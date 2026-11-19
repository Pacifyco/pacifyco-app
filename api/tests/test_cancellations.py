# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Cancellations (CLAUDE.md 6.5 and 9 "Cancellations"; phase 7).

- Parent, 3 hours or more before the start: refunded in full. Less than 3 hours: the whole booking is
  charged (no refund; a payment still being checked is kept, or owed if it's rejected).
- Sitter, 8 hours or more before the start: the parent is refunded, no penalty. Less than 8 hours: the
  parent is refunded, she earns nothing and gets a strike.
- Exactly 3 (or 8) hours before counts as in time.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import cancellations
from tests.test_admin_payments import confirm, paid, payment_id, reject, verify_children  # noqa: F401
from tests.test_auto_cancel import move, status
from tests.test_bookings import book, child_of, children_of, free_sitter, options  # noqa: F401  (fixtures)
from tests.test_documents import admin, client, parent, row, rows, scalar, storage  # noqa: F401  (fixtures)
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_payments import booking, get, pay  # noqa: F401  (fixture)
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import auth_for, user  # noqa: F401  (fixture)
from tests.test_sitter_bookings import signed_in
from tests.test_verification import reviewer  # noqa: F401  (fixture)


def parent_cancels(client, who, booking_id):
    return client.post(f"/parent/bookings/{booking_id}/cancel", headers=auth_for(who))


def sitter_cancels(client, who, booking_id):
    return client.post(f"/sitter/bookings/{booking_id}/cancel", headers=auth_for(who))


def payments_of(db_engine, booking_id, kind):
    return rows(
        db_engine,
        "SELECT * FROM payments WHERE booking_id = :b AND kind = :k ORDER BY created_at",
        b=booking_id,
        k=kind,
    )


@pytest.fixture
def confirmed(client, reviewer, db_engine, booking, finished_parent, paid):
    """The booking, paid and confirmed (every child verified)."""
    verify_children(db_engine, finished_parent["id"])
    assert confirm(client, reviewer, paid).json()["booking_status"] == "confirmed"
    return booking


def to(mailbox, address):
    return [email for email in mailbox.sent if email.to == address]


# ---------- the boundaries, exactly (6.5) ----------


@pytest.mark.parametrize(
    ("before_start", "expected"),
    [
        (timedelta(hours=3), "cancelled_parent"),
        (timedelta(hours=3) - timedelta(seconds=1), "cancelled_parent_late"),
    ],
)
def test_the_parent_3_hour_boundary(db_engine, confirmed, finished_parent, before_start, expected):
    starts = datetime.fromisoformat(confirmed["starts_at"])
    with Session(db_engine) as db:
        done = cancellations.by_parent(db, finished_parent["id"], uuid.UUID(confirmed["id"]), starts - before_start)
        assert done.booking.status.value == expected
    refunds = payments_of(db_engine, confirmed["id"], "refund")
    assert len(refunds) == (1 if expected == "cancelled_parent" else 0)


@pytest.mark.parametrize(
    ("before_start", "expected", "strikes"),
    [
        (timedelta(hours=8), "cancelled_sitter", 0),
        (timedelta(hours=8) - timedelta(seconds=1), "cancelled_sitter_late", 1),
    ],
)
def test_the_sitter_8_hour_boundary(db_engine, confirmed, before_start, expected, strikes):
    starts = datetime.fromisoformat(confirmed["starts_at"])
    with Session(db_engine) as db:
        done = cancellations.by_sitter(
            db, uuid.UUID(confirmed["sitter_id"]), uuid.UUID(confirmed["id"]), starts - before_start
        )
        assert done.booking.status.value == expected
    assert len(payments_of(db_engine, confirmed["id"], "refund")) == 1  # refunded either way
    assert scalar(db_engine, "SELECT count(*) FROM strikes WHERE booking_id = :b", b=confirmed["id"]) == strikes


# ---------- the parent cancels ----------


def test_in_time_the_parent_is_refunded_and_the_sitter_told(client, db_engine, mailbox, confirmed, finished_parent):
    response = parent_cancels(client, finished_parent, confirmed["id"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled_parent"
    (refund,) = payments_of(db_engine, confirmed["id"], "refund")
    assert refund["amount_paise"] == -confirmed["price_paise"] and refund["status"] == "pending"
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    assert to(mailbox, sitter["email"])[-1].heading == "A family has cancelled a booking."
    audit = row(
        db_engine,
        "SELECT actor_id, after FROM audit_log WHERE action = 'booking_cancelled' AND entity_id = :b",
        b=confirmed["id"],
    )
    assert audit["actor_id"] == finished_parent["id"] and audit["after"]["status"] == "cancelled_parent"
    # Her time is free again.
    start = datetime.fromisoformat(confirmed["starts_at"])
    times = options(client, finished_parent, {"id": confirmed["sitter_id"]})["times"]
    assert any(datetime.fromisoformat(t["starts_at"]) <= start < datetime.fromisoformat(t["ends_at"]) for t in times)


def test_late_the_whole_booking_is_charged(client, db_engine, confirmed, finished_parent):
    move(db_engine, confirmed["id"], datetime.now(UTC) + timedelta(hours=2))
    response = parent_cancels(client, finished_parent, confirmed["id"])
    assert response.json()["status"] == "cancelled_parent_late"
    assert payments_of(db_engine, confirmed["id"], "refund") == []


def test_withdrawing_a_request_charges_nothing_and_tells_no_one(
    client, db_engine, mailbox, finished_parent, free_sitter
):
    sitter = free_sitter("unwind")
    kids = children_of(db_engine, finished_parent["id"])[:1]
    made = book(client, finished_parent, sitter, child_ids=kids).json()
    response = parent_cancels(client, finished_parent, made["id"])
    assert response.json()["status"] == "cancelled_parent"
    assert to(mailbox, sitter["email"]) == []
    assert scalar(db_engine, "SELECT count(*) FROM payments WHERE booking_id = :b", b=made["id"]) == 0


def test_a_payment_still_being_checked_is_refunded_once_confirmed(
    client, reviewer, db_engine, booking, finished_parent, paid
):
    assert parent_cancels(client, finished_parent, booking["id"]).json()["status"] == "cancelled_parent"
    assert confirm(client, reviewer, paid).json()["refund_owed"] is True


def test_late_a_payment_being_checked_is_kept_once_confirmed(
    client, reviewer, db_engine, booking, finished_parent, paid
):
    move(db_engine, booking["id"], datetime.now(UTC) + timedelta(hours=2))
    assert parent_cancels(client, finished_parent, booking["id"]).json()["status"] == "cancelled_parent_late"
    assert confirm(client, reviewer, paid).json()["refund_owed"] is False
    assert payments_of(db_engine, booking["id"], "refund") == []


def test_late_and_the_payment_rejected_the_price_is_owed(client, reviewer, db_engine, booking, finished_parent, paid):
    move(db_engine, booking["id"], datetime.now(UTC) + timedelta(hours=2))
    assert parent_cancels(client, finished_parent, booking["id"]).json()["status"] == "cancelled_parent_late"
    assert reject(client, reviewer, paid).status_code == 200
    (charge,) = payments_of(db_engine, booking["id"], "cancellation_charge")
    assert charge["amount_paise"] == booking["price_paise"] and charge["status"] == "pending"
    history = client.get("/parent/payments", headers=auth_for(finished_parent)).json()
    assert history["owed_paise"] == booking["price_paise"]  # no new bookings until it's paid (6.4)


def test_the_parent_cant_cancel_once_started_or_twice_or_someone_elses(
    client, db_engine, confirmed, finished_parent, free_sitter
):
    stranger = free_sitter("unwind")  # a sitter isn't a parent
    assert client.post(f"/parent/bookings/{confirmed['id']}/cancel", headers=auth_for(stranger)).status_code == 403
    assert parent_cancels(client, finished_parent, uuid.uuid4()).status_code == 404
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(minutes=1))
    started = parent_cancels(client, finished_parent, confirmed["id"])
    assert started.status_code == 409 and started.json()["error"]["code"] == "already_started"
    move(db_engine, confirmed["id"], datetime.now(UTC) + timedelta(hours=10))
    assert parent_cancels(client, finished_parent, confirmed["id"]).status_code == 200
    again = parent_cancels(client, finished_parent, confirmed["id"])
    assert again.status_code == 409 and again.json()["error"]["code"] == "cannot_cancel"


# ---------- the sitter cancels ----------


def test_in_time_no_penalty_and_the_family_is_refunded(client, db_engine, mailbox, confirmed, finished_parent):
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    move(db_engine, confirmed["id"], datetime.now(UTC) + timedelta(hours=9))
    response = sitter_cancels(client, sitter, confirmed["id"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled_sitter"
    assert len(payments_of(db_engine, confirmed["id"], "refund")) == 1
    assert scalar(db_engine, "SELECT count(*) FROM strikes WHERE sitter_id = :s", s=confirmed["sitter_id"]) == 0
    email = to(mailbox, finished_parent["email"])[-1]
    assert "had to cancel your booking" in email.heading and "refund you in full" in email.body


def test_late_she_gets_a_strike(client, db_engine, confirmed, finished_parent):
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    move(db_engine, confirmed["id"], datetime.now(UTC) + timedelta(hours=5))
    assert sitter_cancels(client, sitter, confirmed["id"]).json()["status"] == "cancelled_sitter_late"
    assert len(payments_of(db_engine, confirmed["id"], "refund")) == 1  # the family is still refunded
    strike = row(db_engine, "SELECT * FROM strikes WHERE booking_id = :b", b=confirmed["id"])
    assert str(strike["sitter_id"]) == confirmed["sitter_id"] and strike["reason"] == "late_cancellation"
    assert timedelta(days=181) < strike["expires_at"] - strike["given_at"] < timedelta(days=184)  # 6 months
    assert strike["removed_at"] is None
    assert (
        scalar(
            db_engine,
            "SELECT count(*) FROM audit_log WHERE action = 'strike_given' AND entity_id = :s",
            s=str(strike["id"]),
        )
        == 1
    )


def test_an_accepted_unpaid_booking_charges_nothing(client, db_engine, mailbox, booking, finished_parent):
    sitter = signed_in(db_engine, booking["sitter_id"])
    assert sitter_cancels(client, sitter, booking["id"]).json()["status"] == "cancelled_sitter"
    assert payments_of(db_engine, booking["id"], "refund") == []
    assert "haven't been charged" in to(mailbox, finished_parent["email"])[-1].body


def test_the_admins_are_told_so_they_can_find_a_replacement(client, db_engine, mailbox, confirmed):
    settings = client.app.dependency_overrides  # the test app's settings
    from app.settings import get_settings

    current = settings[get_settings]()
    settings[get_settings] = lambda: current.model_copy(update={"admin_alert_emails": ["ops@example.com"]})
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    assert sitter_cancels(client, sitter, confirmed["id"]).status_code == 200
    (alert,) = to(mailbox, "ops@example.com")
    assert alert.heading == "A sitter cancelled a booking."


def test_she_cant_cancel_a_request_or_someone_elses(client, db_engine, finished_parent, free_sitter, booking):
    sitter = signed_in(db_engine, booking["sitter_id"])
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE bookings SET status = 'requested' WHERE id = :b"), {"b": booking["id"]})
    response = sitter_cancels(client, sitter, booking["id"])
    assert response.status_code == 409 and response.json()["error"]["code"] == "cannot_cancel"  # she declines it
    assert sitter_cancels(client, free_sitter("unwind"), booking["id"]).status_code == 404
    assert client.post(f"/sitter/bookings/{booking['id']}/cancel", headers=auth_for(finished_parent)).status_code == 403
    assert status(db_engine, booking["id"]) == "requested"
