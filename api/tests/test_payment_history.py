# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""The parent's payments (CLAUDE.md 6.1, 6.4 and 9 "Payments"; phase 6 "Parent payment history").

Every payment, charge and refund of theirs, newest first, and only theirs. Unpaid charges (overtime and
cancellation charges, which later phases create) are money owed: no new booking until they're paid.
Booking payments being checked, and refunds, aren't money owed."""

import uuid

import pytest
from sqlalchemy import text

from tests.test_admin_payments import confirm, paid, payment_id, verify_children  # noqa: F401  (fixture)
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_documents import admin, cleanup_documents, client, parent, row, rows, scalar, storage  # noqa: F401
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_payments import booking, pay  # noqa: F401  (fixture)
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, user  # noqa: F401  (fixture)
from tests.test_verification import reviewer  # noqa: F401  (fixture)


def history(client, who):
    response = client.get("/parent/payments", headers=auth_for(who))
    assert response.status_code == 200, response.text
    return response.json()


def charge(db_engine, booking, parent_id, kind="overtime", amount=69_900, status="pending"):
    """A charge as later phases will add it (overtime at check-out, late cancellation)."""
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO payments (booking_id, parent_id, kind, amount_paise, status, rejection_reason) "
                "VALUES (:b, :p, :k, :a, :s, :r)"
            ),
            {
                "b": booking["id"],
                "p": parent_id,
                "k": kind,
                "a": amount,
                "s": status,
                "r": "Not received" if status == "rejected" else None,
            },
        )


def test_nothing_yet(client, finished_parent):
    assert history(client, finished_parent) == {"owed_paise": 0, "payments": []}


def test_the_history_lists_payments_and_refunds_newest_first(
    reviewer, client, db_engine, booking, finished_parent, paid
):
    verify_children(db_engine, finished_parent["id"])
    assert confirm(client, reviewer, paid).status_code == 200
    with db_engine.begin() as conn:  # a refund for it, as if it had been cancelled
        conn.execute(
            text("INSERT INTO payments (booking_id, parent_id, kind, amount_paise) VALUES (:b, :p, 'refund', :a)"),
            {"b": booking["id"], "p": finished_parent["id"], "a": -booking["price_paise"]},
        )
    found = history(client, finished_parent)
    assert found["owed_paise"] == 0  # a refund is money Pacifyco owes them
    refund, payment = found["payments"]
    assert refund["kind"] == "refund" and refund["amount_paise"] == booking["price_paise"]
    assert refund["status"] == "pending"
    assert payment == {
        "id": paid,
        "kind": "booking",
        "amount_paise": booking["price_paise"],
        "status": "confirmed",
        "upi_reference": "123456789012",
        "transfer_reference": None,
        "rejection_reason": None,
        "created_at": payment["created_at"],
        "decided_at": payment["decided_at"],
        "booking_id": booking["id"],
        "booking_starts_at": booking["starts_at"],
        "sitter_name": "Lakshmi Nair",
    }
    assert payment["decided_at"] is not None
    assert "plan" not in str(found).lower()  # never the plan's name (6.1)


def test_a_payment_being_checked_isnt_money_owed(client, db_engine, booking, finished_parent, free_sitter):
    assert pay(client, finished_parent, booking["id"]).status_code == 201
    assert history(client, finished_parent)["owed_paise"] == 0
    kids = children_of(db_engine, finished_parent["id"])
    assert book(client, finished_parent, free_sitter("unwind"), child_ids=kids[:1]).status_code == 201


@pytest.mark.parametrize("kind", ["overtime", "cancellation_charge"])
def test_an_unpaid_charge_blocks_new_bookings(client, db_engine, booking, finished_parent, free_sitter, kind):
    charge(db_engine, booking, finished_parent["id"], kind=kind, amount=69_900)
    assert history(client, finished_parent)["owed_paise"] == 69_900
    sitter = free_sitter("unwind")
    options = client.get(f"/parent/sitters/{sitter['id']}/booking-options", headers=auth_for(finished_parent))
    assert options.json()["owed_paise"] == 69_900
    kids = children_of(db_engine, finished_parent["id"])
    response = book(client, finished_parent, sitter, child_ids=kids[:1])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "money_owed"


def test_a_paid_charge_doesnt(client, db_engine, booking, finished_parent, free_sitter):
    charge(db_engine, booking, finished_parent["id"], status="confirmed")
    assert history(client, finished_parent)["owed_paise"] == 0
    kids = children_of(db_engine, finished_parent["id"])
    assert book(client, finished_parent, free_sitter("unwind"), child_ids=kids[:1]).status_code == 201


def test_only_their_own_payments(client, db_engine, booking, finished_parent):
    assert pay(client, finished_parent, booking["id"]).status_code == 201
    charge(db_engine, booking, finished_parent["id"])
    other = {"id": uuid.uuid4(), "email": f"{uuid.uuid4()}@example.com"}
    try:
        assert client.post("/me/profile", json=PARENT, headers=auth_for(other)).status_code == 201
        assert history(client, other) == {"owed_paise": 0, "payments": []}
    finally:
        cleanup_documents(db_engine, other["id"])


def test_sitters_and_admins_cant_open_it(client, admin):
    from tests.test_documents import as_user

    assert client.get("/parent/payments", headers=as_user(admin)).status_code == 403


def test_money_owed_is_the_sum_of_unpaid_charges(client, db_engine, booking, finished_parent):
    charge(db_engine, booking, finished_parent["id"], kind="overtime", amount=69_900)
    charge(db_engine, booking, finished_parent["id"], kind="cancellation_charge", amount=139_800)
    charge(db_engine, booking, finished_parent["id"], kind="overtime", amount=84_900, status="confirmed")
    charge(db_engine, booking, finished_parent["id"], kind="overtime", amount=10_000, status="rejected")
    with db_engine.begin() as conn:  # a refund owed to them doesn't lower what they owe
        conn.execute(
            text("INSERT INTO payments (booking_id, parent_id, kind, amount_paise) VALUES (:b, :p, 'refund', -50000)"),
            {"b": booking["id"], "p": finished_parent["id"]},
        )
    assert history(client, finished_parent)["owed_paise"] == 69_900 + 139_800
