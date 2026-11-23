# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Admins confirm or reject booking payments, and pay refunds back (CLAUDE.md 6.1, 6.4 and 9 "Plans and
pricing", "Payments", "Bookings"; phase 6).

- Confirming: the booking is `confirmed` if every child on it is verified, else `awaiting_verification`,
  which becomes `confirmed` when the last child is approved. Until then it doesn't hold her time (Reuben,
  2026-11-18). Once confirmed, other unpaid or unverified bookings with her for an overlapping time are
  cancelled (paid ones refunded) and their parents told.
- A paid booking whose start comes with a child still unverified is cancelled and refunded.
- If another booking already holds the time, the money is still recorded, the booking is cancelled and a
  refund is owed; an admin pays it back and records the transfer reference.
- Rejecting needs a reason the parent sees; they can send a new reference before the deadline.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from tests.test_auto_cancel import move, status
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_checklists import CONTACTS
from tests.test_documents import (  # noqa: F401  (fixtures)
    accept_consent,
    add_child,
    admin,
    as_user,
    cleanup_documents,
    client,
    parent,
    row,
    rows,
    scalar,
    storage,
)
from tests.test_marketplace import at, finished_parent, india_day, make_sitter  # noqa: F401  (fixtures)
from tests.test_payments import booking, get, pay  # noqa: F401  (fixture)
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, fill_details, user  # noqa: F401  (fixture)
from tests.test_verification import review, reviewer, upload  # noqa: F401  (fixture)


def queue(client, admin_id):
    response = client.get("/admin/payments", headers=as_user(admin_id))
    assert response.status_code == 200, response.text
    return response.json()


def payment_id(db_engine, booking_id, kind="booking"):
    return str(
        scalar(
            db_engine,
            "SELECT id FROM payments WHERE booking_id = :b AND kind = :k ORDER BY created_at DESC LIMIT 1",
            b=booking_id,
            k=kind,
        )
    )


def confirm(client, admin_id, pid):
    return client.post(f"/admin/payments/{pid}/confirm", headers=as_user(admin_id))


def reject(client, admin_id, pid, reason="We haven't received it."):
    return client.post(f"/admin/payments/{pid}/reject", json={"reason": reason}, headers=as_user(admin_id))


def verify_children(db_engine, parent_id):
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE children SET verification_status = 'approved' WHERE parent_id = :p"), {"p": parent_id}
        )


@pytest.fixture
def paid(client, reviewer, db_engine, booking, finished_parent):
    """The booking's UPI reference has been sent and waits for an admin."""
    assert pay(client, finished_parent, booking["id"]).status_code == 201
    return payment_id(db_engine, booking["id"])


# ---------- the queue ----------


def test_admins_see_payments_to_check(client, reviewer, db_engine, booking, finished_parent, paid):
    found = queue(client, reviewer)
    item = next(item for item in found["to_check"] if item["id"] == paid)
    assert item["booking_id"] == booking["id"]
    assert item["amount_paise"] == booking["price_paise"]
    assert item["upi_reference"] == "123456789012"
    assert item["note"] == f"Pacifyco booking {booking['id'][:8].upper()}"
    assert item["plan"] == "unwind"  # admins see the plan; parents never do
    assert item["children_verified"] is False
    assert item["parent_email"] == finished_parent["email"]


def test_parents_and_sitters_cant_see_or_decide_payments(client, db_engine, finished_parent, paid):
    assert client.get("/admin/payments", headers=auth_for(finished_parent)).status_code == 403
    response = client.post(f"/admin/payments/{paid}/confirm", headers=auth_for(finished_parent))
    assert response.status_code == 403
    assert status(db_engine, payment_booking(db_engine, paid)) == "pending_payment"


def payment_booking(db_engine, pid):
    return str(scalar(db_engine, "SELECT booking_id FROM payments WHERE id = :p", p=pid))


# ---------- confirming ----------


def test_confirmed_and_verified_the_booking_is_confirmed(
    client, reviewer, db_engine, mailbox, booking, finished_parent, paid
):
    verify_children(db_engine, finished_parent["id"])
    response = confirm(client, reviewer, paid)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "status": "confirmed",
        "booking_status": "confirmed",
        "refund_owed": False,
        "cancelled_bookings": 0,
    }
    saved = row(db_engine, "SELECT status, confirmed_by, confirmed_at FROM payments WHERE id = :p", p=paid)
    assert saved["status"] == "confirmed" and saved["confirmed_by"] == reviewer and saved["confirmed_at"]
    assert get(client, finished_parent, booking["id"]).json()["status"] == "confirmed"
    actions = {
        item["action"]
        for item in rows(db_engine, "SELECT action FROM audit_log WHERE entity_id IN (:b, :p)", b=booking["id"], p=paid)
    }
    assert {"payment_confirmed", "booking_paid"} <= actions
    (email,) = [item for item in mailbox.sent if item.to == finished_parent["email"]]
    assert email.heading == "Your booking is confirmed."
    assert mailbox.sent[-1].subject == "Your Pacifyco booking is confirmed"  # and the sitter (phase 11)
    assert email.button_url.endswith(f"/parent/bookings/{booking['id']}")


def offered(client, who, booking) -> bool:
    """The booking's start is still among her bookable times."""
    path = f"/parent/sitters/{booking['sitter_id']}/booking-options"
    times = client.get(path, headers=auth_for(who)).json()["times"]
    start = datetime.fromisoformat(booking["starts_at"])
    return any(datetime.fromisoformat(t["starts_at"]) <= start < datetime.fromisoformat(t["ends_at"]) for t in times)


def refunds(db_engine, booking_id):
    return rows(db_engine, "SELECT * FROM payments WHERE booking_id = :b AND kind = 'refund'", b=booking_id)


def test_paid_with_a_child_unverified_it_doesnt_hold_the_time_until_the_child_is_approved(
    client, reviewer, db_engine, mailbox, booking, finished_parent, paid
):
    assert confirm(client, reviewer, paid).json()["booking_status"] == "awaiting_verification"
    assert "isn't kept for you" in mailbox.sent[-1].body
    # Her time stays free until every child is verified (Reuben, 2026-11-18).
    assert offered(client, finished_parent, booking)

    child = children_of(db_engine, finished_parent["id"])[0]
    assert review(client, reviewer, f"/admin/children/{child}/decision").status_code == 200
    assert status(db_engine, booking["id"]) == "confirmed"
    assert not offered(client, finished_parent, booking)
    audit = row(
        db_engine,
        "SELECT actor_id, after FROM audit_log WHERE action = 'booking_confirmed' AND entity_id = :b",
        b=booking["id"],
    )
    assert audit["actor_id"] == reviewer and audit["after"]["reason"] == "children_verified"


@pytest.fixture
def another_family(client, db_engine, storage):
    """A second parent with a finished profile and one child (not yet verified)."""
    other = {"id": uuid.uuid4(), "email": f"{uuid.uuid4()}@example.com"}
    assert client.post("/me/profile", json=PARENT, headers=auth_for(other)).status_code == 201
    assert fill_details(client, other).status_code == 200
    accept_consent(client, other)
    kid = add_child(db_engine, other["id"])
    upload(client, storage, other, "birth_certificate", kid)
    put = client.put("/parent/emergency-contacts", json={"contacts": CONTACTS}, headers=auth_for(other))
    assert put.status_code == 200
    yield other, str(kid)
    cleanup_documents(db_engine, other["id"])


def older_overlap(client, db_engine, other, kid, booking) -> dict:
    """Another family's booking for the same time, waiting for payment, as could happen before requests
    held her time (CLAUDE.md 6.4): made while ours didn't hold it."""
    ours = status(db_engine, booking["id"])
    set_booking_status(db_engine, booking["id"], "requested")
    theirs = book(client, other, {"id": booking["sitter_id"]}, child_ids=[kid])
    assert theirs.status_code == 201, theirs.text
    set_booking_status(db_engine, booking["id"], ours)
    set_booking_status(db_engine, theirs.json()["id"], "pending_payment")
    return theirs.json()


def set_booking_status(db_engine, booking_id, value) -> None:
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE bookings SET status = :s WHERE id = :b"), {"s": value, "b": booking_id})


def test_the_first_confirmed_payment_wins_and_the_others_are_cancelled(
    client, reviewer, db_engine, mailbox, booking, finished_parent, paid, another_family
):
    other, kid = another_family
    # Another family's older booking for the same time, paid too.
    theirs = older_overlap(client, db_engine, other, kid, booking)
    assert pay(client, other, theirs["id"], "999999999999").status_code == 201

    verify_children(db_engine, finished_parent["id"])
    result = confirm(client, reviewer, paid).json()
    assert result["booking_status"] == "confirmed" and result["cancelled_bookings"] == 1
    assert status(db_engine, theirs["id"]) == "cancelled_slot_taken"
    told = [email for email in mailbox.sent if email.to == other["email"]]
    assert told and "confirmed first" in told[-1].body and "refund you in full" in told[-1].body

    # Their payment, confirmed later, is money in for a booking that can't go ahead: a refund.
    late = confirm(client, reviewer, payment_id(db_engine, theirs["id"])).json()
    assert late == {
        "status": "confirmed",
        "booking_status": "cancelled_slot_taken",
        "refund_owed": True,
        "cancelled_bookings": 0,
    }
    refund = row(db_engine, "SELECT * FROM payments WHERE booking_id = :b AND kind = 'refund'", b=theirs["id"])
    assert refund["amount_paise"] == -theirs["price_paise"] and refund["status"] == "pending"
    owed = next(item for item in queue(client, reviewer)["refunds"] if item["id"] == str(refund["id"]))
    assert owed["amount_paise"] == theirs["price_paise"]
    assert owed["paid_with_reference"] == "999999999999"

    # Paid back, with the transfer's reference.
    response = client.post(
        f"/admin/refunds/{refund['id']}/paid", json={"transfer_reference": " UTR 4455 "}, headers=as_user(reviewer)
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "confirmed", "transfer_reference": "UTR 4455"}
    assert mailbox.sent[-1].to == other["email"] and "refunded" in mailbox.sent[-1].heading
    again = client.post(
        f"/admin/refunds/{refund['id']}/paid", json={"transfer_reference": "x"}, headers=as_user(reviewer)
    )
    assert again.status_code == 409


def test_a_paid_booking_waiting_for_verification_loses_the_time_to_one_confirmed_first(
    client, reviewer, db_engine, mailbox, booking, finished_parent, paid, another_family
):
    assert confirm(client, reviewer, paid).json()["booking_status"] == "awaiting_verification"
    other, kid = another_family
    # Her time is still free, so the other family can book it, and their children are verified.
    theirs = older_overlap(client, db_engine, other, kid, booking)
    assert pay(client, other, theirs["id"], "999999999999").status_code == 201
    verify_children(db_engine, other["id"])

    result = confirm(client, reviewer, payment_id(db_engine, theirs["id"])).json()
    assert result["booking_status"] == "confirmed" and result["cancelled_bookings"] == 1
    assert status(db_engine, booking["id"]) == "cancelled_slot_taken"
    (refund,) = refunds(db_engine, booking["id"])
    assert refund["amount_paise"] == -booking["price_paise"] and refund["status"] == "pending"
    told = [email for email in mailbox.sent if email.to == finished_parent["email"]]
    assert "confirmed first" in told[-1].body and "refund you in full" in told[-1].body

    # Approving their child later changes nothing.
    child = children_of(db_engine, finished_parent["id"])[0]
    assert review(client, reviewer, f"/admin/children/{child}/decision").status_code == 200
    assert status(db_engine, booking["id"]) == "cancelled_slot_taken"
    assert len(refunds(db_engine, booking["id"])) == 1


def test_once_the_child_is_approved_the_booking_takes_the_time(
    client, reviewer, db_engine, mailbox, booking, finished_parent, paid, another_family
):
    assert confirm(client, reviewer, paid).json()["booking_status"] == "awaiting_verification"
    other, kid = another_family
    theirs = book(client, other, {"id": booking["sitter_id"]}, child_ids=[kid]).json()

    child = children_of(db_engine, finished_parent["id"])[0]
    assert review(client, reviewer, f"/admin/children/{child}/decision").status_code == 200
    assert status(db_engine, booking["id"]) == "confirmed"
    assert status(db_engine, theirs["id"]) == "cancelled_slot_taken"
    assert refunds(db_engine, theirs["id"]) == []  # they hadn't paid
    told = [email for email in mailbox.sent if email.to == other["email"]]
    assert told and "confirmed first" in told[-1].body and "refund" not in told[-1].body


def test_a_child_approved_after_another_booking_took_the_time_is_refunded(
    client, reviewer, db_engine, mailbox, booking, finished_parent, paid, another_family
):
    assert confirm(client, reviewer, paid).json()["booking_status"] == "awaiting_verification"
    other, kid = another_family
    theirs = book(client, other, {"id": booking["sitter_id"]}, child_ids=[kid]).json()
    with db_engine.begin() as conn:  # confirmed some other way, leaving ours waiting
        conn.execute(text("UPDATE bookings SET status = 'confirmed' WHERE id = :b"), {"b": theirs["id"]})

    child = children_of(db_engine, finished_parent["id"])[0]
    assert review(client, reviewer, f"/admin/children/{child}/decision").status_code == 200
    assert status(db_engine, booking["id"]) == "cancelled_slot_taken"
    assert len(refunds(db_engine, booking["id"])) == 1
    audit = row(
        db_engine,
        "SELECT before, after FROM audit_log WHERE action = 'booking_cancelled' AND entity_id = :b",
        b=booking["id"],
    )
    assert audit["before"] == {"status": "awaiting_verification"}
    assert audit["after"] == {"status": "cancelled_slot_taken", "taken_by": theirs["id"]}
    told = [email.body for email in mailbox.sent if email.to == finished_parent["email"]]
    assert any("confirmed first" in body and "refund you in full" in body for body in told)


def test_paid_but_unverified_at_the_start_it_is_cancelled_and_refunded(
    client, reviewer, db_engine, booking, finished_parent, paid
):
    assert confirm(client, reviewer, paid).json()["booking_status"] == "awaiting_verification"
    move(db_engine, booking["id"], datetime.now(UTC) - timedelta(minutes=5))
    # Opened by the parent: cancelled at once, not at the next job run.
    assert get(client, finished_parent, booking["id"]).json()["status"] == "cancelled_unverified"
    (refund,) = refunds(db_engine, booking["id"])
    assert refund["amount_paise"] == -booking["price_paise"] and refund["status"] == "pending"
    audit = row(
        db_engine,
        "SELECT actor_id, before, after FROM audit_log WHERE action = 'booking_cancelled' AND entity_id = :b",
        b=booking["id"],
    )
    assert audit["actor_id"] is None and audit["before"] == {"status": "awaiting_verification"}
    assert audit["after"] == {"status": "cancelled_unverified", "reason": "children_not_verified_by_start"}
    # Approving the child now confirms nothing, and nothing is refunded twice.
    child = children_of(db_engine, finished_parent["id"])[0]
    assert review(client, reviewer, f"/admin/children/{child}/decision").status_code == 200
    assert status(db_engine, booking["id"]) == "cancelled_unverified"
    assert len(refunds(db_engine, booking["id"])) == 1


def test_the_frequent_run_cancels_unverified_bookings_at_the_start(client, reviewer, db_engine, booking, paid):
    from tests.test_jobs import SECRET, bearer
    from tests.test_jobs import client as jobs_client

    assert confirm(client, reviewer, paid).json()["booking_status"] == "awaiting_verification"
    move(db_engine, booking["id"], datetime.now(UTC) + timedelta(minutes=30))
    run = jobs_client(db_engine).post("/internal/jobs/frequent", headers=bearer(SECRET))
    assert run.status_code == 200
    assert status(db_engine, booking["id"]) == "awaiting_verification"  # not started yet
    move(db_engine, booking["id"], datetime.now(UTC) - timedelta(minutes=1))
    for _ in range(2):  # idempotent
        assert jobs_client(db_engine).post("/internal/jobs/frequent", headers=bearer(SECRET)).status_code == 200
    assert status(db_engine, booking["id"]) == "cancelled_unverified"
    assert len(refunds(db_engine, booking["id"])) == 1


def test_a_payment_is_decided_once(client, reviewer, db_engine, finished_parent, paid):
    verify_children(db_engine, finished_parent["id"])
    assert confirm(client, reviewer, paid).status_code == 200
    for again in (confirm(client, reviewer, paid), reject(client, reviewer, paid)):
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "payment_already_decided"


def test_a_booking_that_has_started_cant_be_confirmed(client, reviewer, db_engine, booking, paid):
    move(db_engine, booking["id"], datetime.now(UTC) - timedelta(minutes=5))
    response = confirm(client, reviewer, paid)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "booking_started"
    assert scalar(db_engine, "SELECT status FROM payments WHERE id = :p", p=paid) == "pending"


def test_unknown_payment_is_404(client, reviewer):
    assert confirm(client, reviewer, uuid.uuid4()).status_code == 404


# ---------- rejecting ----------


def test_a_rejected_payment_shows_the_reason_and_can_be_sent_again(
    client, reviewer, db_engine, mailbox, booking, finished_parent, paid
):
    response = reject(client, reviewer, paid, "  The reference doesn't match any payment.  ")
    assert response.status_code == 200, response.text
    assert response.json()["booking_status"] == "pending_payment"
    shown = get(client, finished_parent, booking["id"]).json()["payment"]
    assert shown == {
        "status": "rejected",
        "upi_reference": "123456789012",
        "sent_at": shown["sent_at"],
        "rejection_reason": "The reference doesn't match any payment.",
    }
    email = mailbox.sent[-1]
    assert email.to == finished_parent["email"] and "doesn't match any payment" in email.body
    assert pay(client, finished_parent, booking["id"], "222222222222").status_code == 201


@pytest.mark.parametrize("reason", ["", "   "])
def test_rejecting_needs_a_reason(client, reviewer, paid, reason):
    assert reject(client, reviewer, paid, reason).status_code == 422


def test_rejected_after_the_deadline_the_booking_is_cancelled(client, reviewer, db_engine, booking, paid):
    move(db_engine, booking["id"], datetime.now(UTC) + timedelta(hours=2))
    assert reject(client, reviewer, paid).json()["booking_status"] == "cancelled_unpaid"


# ---------- money rows ----------


def test_a_refund_needs_a_transfer_reference(client, reviewer, db_engine, booking, finished_parent, paid):
    # A refund row is only made by a confirmation; this one is made directly for the check.
    with db_engine.begin() as conn:
        refund_id = conn.execute(
            text(
                "INSERT INTO payments (booking_id, parent_id, kind, amount_paise) "
                "VALUES (:b, :p, 'refund', :a) RETURNING id"
            ),
            {"b": booking["id"], "p": finished_parent["id"], "a": -booking["price_paise"]},
        ).scalar_one()
    response = client.post(
        f"/admin/refunds/{refund_id}/paid", json={"transfer_reference": "   "}, headers=as_user(reviewer)
    )
    assert response.status_code == 422
    with db_engine.connect() as conn, pytest.raises(Exception, match="refund_paid_has_reference"):
        conn.execute(text("UPDATE payments SET status = 'confirmed' WHERE id = :r"), {"r": refund_id})
    # Paying a booking payment's id as a refund is "not found".
    response = client.post(f"/admin/refunds/{paid}/paid", json={"transfer_reference": "x"}, headers=as_user(reviewer))
    assert response.status_code == 404
