# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Paying a charge (CLAUDE.md 6.5; overtime uses the same flow in phase 8).

A charge is money owed: no new bookings until it's paid (6.4). The parent pays it by UPI and sends the
12-digit reference; an admin confirms it (paid, no longer owed) or rejects the reference (cleared, the
reason shown, still owed). Until an admin confirms it, it's still owed."""

import uuid
from urllib.parse import parse_qs, urlsplit

import pytest

from tests.test_admin_payments import confirm, queue, reject, verify_children  # noqa: F401
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_documents import admin, as_user, cleanup_documents, client, parent, row, rows, scalar, storage  # noqa: F401
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_payment_history import charge, history
from tests.test_payments import booking, upi_set  # noqa: F401  (fixtures)
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, user  # noqa: F401  (fixture)
from tests.test_verification import reviewer  # noqa: F401  (fixture)


@pytest.fixture
def owed(db_engine, booking, finished_parent):
    """A late cancellation's charge the parent owes."""
    charge(db_engine, booking, finished_parent["id"], kind="cancellation_charge", amount=139_800)
    return str(
        scalar(
            db_engine, "SELECT id FROM payments WHERE booking_id = :b AND kind = 'cancellation_charge'", b=booking["id"]
        )
    )


def open_charge(client, who, charge_id):
    return client.get(f"/parent/payments/{charge_id}", headers=auth_for(who))


def send(client, who, charge_id, reference="555566667777"):
    return client.post(
        f"/parent/payments/{charge_id}/payment", json={"upi_reference": reference}, headers=auth_for(who)
    )


def can_book(client, db_engine, who, free_sitter) -> int:
    kids = children_of(db_engine, who["id"])[:1]
    return book(client, who, free_sitter("unwind"), child_ids=kids).status_code


def test_the_charge_says_how_to_pay(client, upi_set, finished_parent, booking, owed):
    found = open_charge(client, finished_parent, owed).json()
    assert found["kind"] == "cancellation_charge" and found["amount_paise"] == 139_800
    assert found["status"] == "pending" and found["upi_reference"] is None
    assert found["booking_id"] == booking["id"] and found["sitter_name"] == "Lakshmi Nair"
    upi = found["pay_by_upi"]
    assert upi["note"] == f"Pacifyco charge {owed[:8].upper()}"
    query = parse_qs(urlsplit(upi["upi_link"]).query)
    assert query["am"] == ["1398.00"] and query["tn"] == [upi["note"]]
    assert "plan" not in str(found).lower()


def test_sending_the_reference_waits_for_an_admin_and_its_still_owed(
    client, db_engine, free_sitter, finished_parent, owed
):
    response = send(client, finished_parent, owed)
    assert response.status_code == 201, response.text
    assert response.json()["upi_reference"] == "555566667777" and response.json()["pay_by_upi"] is None
    assert history(client, finished_parent)["owed_paise"] == 139_800  # still owed until it's checked
    assert can_book(client, db_engine, finished_parent, free_sitter) == 409
    again = send(client, finished_parent, owed, "111122223333")
    assert again.status_code == 409 and again.json()["error"]["code"] == "payment_already_sent"


def test_confirmed_its_paid_and_the_parent_can_book(
    client, reviewer, db_engine, mailbox, free_sitter, finished_parent, owed
):
    assert send(client, finished_parent, owed).status_code == 201
    item = next(item for item in queue(client, reviewer)["to_check"] if item["id"] == owed)
    assert item["kind"] == "cancellation_charge" and item["upi_reference"] == "555566667777"
    assert item["note"] == f"Pacifyco charge {owed[:8].upper()}" and item["amount_paise"] == 139_800

    response = confirm(client, reviewer, owed)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "confirmed"
    saved = row(db_engine, "SELECT status, confirmed_by FROM payments WHERE id = :p", p=owed)
    assert saved["status"] == "confirmed" and saved["confirmed_by"] == reviewer
    assert history(client, finished_parent)["owed_paise"] == 0
    assert can_book(client, db_engine, finished_parent, free_sitter) == 201
    assert any(e.to == finished_parent["email"] and e.heading == "We've received your ₹1,398." for e in mailbox.sent)
    assert confirm(client, reviewer, owed).status_code == 409  # decided once


def test_rejected_the_reference_is_cleared_and_can_be_sent_again(
    client, reviewer, db_engine, mailbox, finished_parent, owed
):
    assert send(client, finished_parent, owed).status_code == 201
    response = reject(client, reviewer, owed, "No such payment arrived.")
    assert response.status_code == 200, response.text
    found = open_charge(client, finished_parent, owed).json()
    assert found["status"] == "pending" and found["upi_reference"] is None
    assert found["rejection_reason"] == "No such payment arrived."
    assert history(client, finished_parent)["owed_paise"] == 139_800
    email = mailbox.sent[-1]
    assert email.to == finished_parent["email"] and "No such payment arrived." in email.body
    assert email.button_url.endswith(f"/parent/payments/{owed}")
    assert owed not in [item["id"] for item in queue(client, reviewer)["to_check"]]
    # The same reference may be sent again once it's been rejected (it wasn't used).
    assert send(client, finished_parent, owed).status_code == 201
    assert open_charge(client, finished_parent, owed).json()["rejection_reason"] is None


def test_references_are_checked(client, db_engine, finished_parent, booking, owed):
    bad = send(client, finished_parent, owed, "12345")
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_upi_reference"
    from tests.test_payments import pay

    assert pay(client, finished_parent, booking["id"], "999900001111").status_code == 201  # used for the booking
    used = send(client, finished_parent, owed, "999900001111")
    assert used.status_code == 409 and used.json()["error"]["code"] == "upi_reference_used"


def test_only_their_own_charges(client, db_engine, finished_parent, booking, owed):
    other = {"id": uuid.uuid4(), "email": f"{uuid.uuid4()}@example.com"}
    try:
        assert client.post("/me/profile", json=PARENT, headers=auth_for(other)).status_code == 201
        assert open_charge(client, other, owed).status_code == 404
        assert send(client, other, owed).status_code == 404
    finally:
        cleanup_documents(db_engine, other["id"])
    # A booking payment isn't a charge.
    from tests.test_payments import pay

    assert pay(client, finished_parent, booking["id"]).status_code == 201
    booking_payment = scalar(
        db_engine, "SELECT id FROM payments WHERE booking_id = :b AND kind = 'booking'", b=booking["id"]
    )
    assert open_charge(client, finished_parent, booking_payment).status_code == 404
