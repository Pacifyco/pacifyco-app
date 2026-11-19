# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Paying for a booking (CLAUDE.md 6.1, 9 "Plans and pricing" and "Payments"; phase 6 "Booking payment").

The parent pays the full price by UPI to Pacifyco's UPI ID, from a `upi://pay` link or its QR code, and
enters the 12-digit UPI reference: a `pending` payment row for an admin to check. The booking stays
`pending_payment` until then. Payment rows are append-only."""

import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import text

from app.settings import get_settings
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_documents import cleanup_documents, client, parent, row, rows, scalar, storage  # noqa: F401  (fixtures)
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_sign_up import PARENT, auth_for, user  # noqa: F401  (fixture)

UPI_ID = "pacifyco-test@okaxis"


@pytest.fixture
def upi_set(client):
    """Pacifyco's UPI ID is set (`PACIFY_UPI_ID`)."""
    settings = client.app.dependency_overrides[get_settings]()
    client.app.dependency_overrides[get_settings] = lambda: settings.model_copy(update={"pacify_upi_id": UPI_ID})


@pytest.fixture
def booking(client, db_engine, finished_parent, free_sitter):
    """A 2-hour booking with one child at Unwind's price, accepted by the sitter and waiting for payment.

    Accepted directly in the database, with the child still unverified, so the payment tests also cover
    older bookings that can still reach `awaiting_verification` (CLAUDE.md 6.4). The request flow itself
    is tested in test_requests.py."""
    sitter = free_sitter("unwind")
    kids = children_of(db_engine, finished_parent["id"])
    response = book(client, finished_parent, sitter, child_ids=kids[:1])
    assert response.status_code == 201, response.text
    made = response.json()
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE bookings SET status = 'pending_payment' WHERE id = :b"), {"b": made["id"]})
    made["status"] = "pending_payment"
    return made


def pay(client, who, booking_id, reference="123456789012"):
    return client.post(
        f"/parent/bookings/{booking_id}/payment", json={"upi_reference": reference}, headers=auth_for(who)
    )


def get(client, who, booking_id):
    return client.get(f"/parent/bookings/{booking_id}", headers=auth_for(who))


# ---------- how to pay ----------


def test_a_booking_shows_how_to_pay_by_upi(client, upi_set, booking, finished_parent):
    found = get(client, finished_parent, booking["id"]).json()
    assert found["payment"] is None
    upi = found["pay_by_upi"]
    assert upi["upi_id"] == UPI_ID
    assert upi["payee_name"] == "Pacifyco"
    assert upi["amount_paise"] == booking["price_paise"] == 69_900 * 2
    assert upi["note"] == f"Pacifyco booking {booking['id'][:8].upper()}"

    link = urlsplit(upi["upi_link"])
    assert link.scheme == "upi" and link.netloc == "pay"
    assert parse_qs(link.query) == {
        "pa": [UPI_ID],
        "pn": ["Pacifyco"],
        "am": ["1398.00"],
        "cu": ["INR"],
        "tn": [upi["note"]],
    }
    assert "%20" in link.query and "+" not in link.query  # spaces encoded the way UPI apps read them


def accepted(db_engine, booking_id) -> None:
    """As if the sitter had accepted the request (the request flow is in test_requests.py)."""
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE bookings SET status = 'pending_payment' WHERE id = :b"), {"b": booking_id})


def test_how_to_pay_only_once_the_sitter_accepts(client, upi_set, db_engine, finished_parent, free_sitter):
    kids = children_of(db_engine, finished_parent["id"])
    made = book(client, finished_parent, free_sitter("pause"), child_ids=kids[:1]).json()
    assert made["pay_by_upi"] is None  # a request: nothing to pay yet (6.4)
    assert pay(client, finished_parent, made["id"]).status_code == 409
    accepted(db_engine, made["id"])
    shown = get(client, finished_parent, made["id"]).json()
    assert parse_qs(urlsplit(shown["pay_by_upi"]["upi_link"]).query)["am"] == ["998.00"]  # Pause, 2 hours


def test_no_upi_details_until_pacifycos_upi_id_is_set(client, booking, finished_parent):
    assert get(client, finished_parent, booking["id"]).json()["pay_by_upi"] is None


# ---------- sending the UPI reference ----------


def test_the_upi_reference_adds_a_pending_payment(client, db_engine, upi_set, booking, finished_parent):
    response = pay(client, finished_parent, booking["id"], " 123456789012 ")
    assert response.status_code == 201, response.text
    found = response.json()
    assert found["status"] == "pending_payment"  # waits for an admin to check it
    assert found["payment"]["status"] == "pending"
    assert found["payment"]["upi_reference"] == "123456789012"
    assert found["pay_by_upi"] is not None  # still shown until the booking is confirmed

    saved = row(db_engine, "SELECT * FROM payments WHERE booking_id = :b", b=booking["id"])
    assert saved["kind"] == "booking"
    assert saved["amount_paise"] == booking["price_paise"]
    assert saved["parent_id"] == finished_parent["id"]
    assert saved["due_by"] == datetime.fromisoformat(booking["pay_by"])
    assert saved["confirmed_by"] is None and saved["confirmed_at"] is None
    audit = row(db_engine, "SELECT * FROM audit_log WHERE entity = 'payment' AND entity_id = :id", id=str(saved["id"]))
    assert audit["action"] == "payment_submitted"
    assert audit["actor_id"] == finished_parent["id"]
    assert audit["after"]["amount_paise"] == booking["price_paise"]


@pytest.mark.parametrize("reference", ["12345678901", "1234567890123", "12345678901A", "", "1234 5678 9012"])
def test_the_reference_is_12_digits(client, booking, finished_parent, reference):
    response = pay(client, finished_parent, booking["id"], reference)
    assert response.status_code == 422
    assert response.json()["error"]["code"] in ("invalid_upi_reference", "validation_error")


def test_a_payment_is_sent_once(client, db_engine, booking, finished_parent):
    assert pay(client, finished_parent, booking["id"]).status_code == 201
    again = pay(client, finished_parent, booking["id"], "999999999999")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "payment_already_sent"
    assert scalar(db_engine, "SELECT count(*) FROM payments WHERE booking_id = :b", b=booking["id"]) == 1


def test_after_a_rejection_a_new_reference_can_be_sent(client, db_engine, booking, finished_parent):
    assert pay(client, finished_parent, booking["id"]).status_code == 201
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE payments SET status = 'rejected', rejection_reason = 'Not received' WHERE booking_id = :b"),
            {"b": booking["id"]},
        )
    shown = get(client, finished_parent, booking["id"]).json()["payment"]
    assert shown["status"] == "rejected" and shown["rejection_reason"] == "Not received"
    # The same reference again is allowed once rejected (it may have been typed wrong the first time).
    response = pay(client, finished_parent, booking["id"])
    assert response.status_code == 201, response.text
    assert response.json()["payment"]["status"] == "pending"
    assert scalar(db_engine, "SELECT count(*) FROM payments WHERE booking_id = :b", b=booking["id"]) == 2


def test_one_upi_reference_pays_for_one_booking(client, db_engine, booking, finished_parent, free_sitter):
    kids = children_of(db_engine, finished_parent["id"])
    other = book(client, finished_parent, free_sitter("unwind"), child_ids=kids[:1]).json()
    accepted(db_engine, other["id"])
    assert pay(client, finished_parent, booking["id"]).status_code == 201
    response = pay(client, finished_parent, other["id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "upi_reference_used"


def test_no_payment_after_the_deadline(client, db_engine, booking, finished_parent):
    soon = datetime.now(UTC) + timedelta(hours=2, minutes=59)  # pay by is 3 hours before the start
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE bookings SET starts_at = :s, ends_at = :e WHERE id = :b"),
            {"s": soon, "e": soon + timedelta(hours=2), "b": booking["id"]},
        )
    response = pay(client, finished_parent, booking["id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "payment_deadline_passed"


def test_only_a_booking_waiting_for_payment_can_be_paid(client, db_engine, booking, finished_parent):
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE bookings SET status = 'cancelled_parent' WHERE id = :b"), {"b": booking["id"]})
    response = pay(client, finished_parent, booking["id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_waiting_for_payment"
    assert get(client, finished_parent, booking["id"]).json()["pay_by_upi"] is None


def test_another_parents_booking_is_not_found(client, db_engine, booking):
    other = {"id": uuid.uuid4(), "email": f"{uuid.uuid4()}@example.com"}
    try:
        assert client.post("/me/profile", json=PARENT, headers=auth_for(other)).status_code == 201
        response = pay(client, other, booking["id"])
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
    finally:
        cleanup_documents(db_engine, other["id"])
    assert scalar(db_engine, "SELECT count(*) FROM payments WHERE booking_id = :b", b=booking["id"]) == 0


# ---------- payment rows are money records ----------


def test_the_api_role_cannot_change_an_amount_or_delete_a_payment(client, db_engine, booking, finished_parent):
    assert pay(client, finished_parent, booking["id"]).status_code == 201
    for statement in (
        "UPDATE payments SET amount_paise = 1 WHERE booking_id = :b",
        # (A charge's UPI reference may be set and cleared since 2026-11-19, so it isn't here; test_charges.)
        "UPDATE payments SET kind = 'refund' WHERE booking_id = :b",
        "UPDATE payments SET parent_id = booking_id WHERE booking_id = :b",
        "DELETE FROM payments WHERE booking_id = :b",
    ):
        with db_engine.connect() as conn, pytest.raises(Exception, match="permission denied"):
            conn.execute(text("SET ROLE pacifyco_api"))
            conn.execute(text(statement), {"b": booking["id"]})
    with db_engine.begin() as conn:
        conn.execute(text("SET LOCAL ROLE pacifyco_api"))
        conn.execute(
            text("UPDATE payments SET status = 'confirmed', confirmed_at = now() WHERE booking_id = :b"),
            {"b": booking["id"]},
        )
    assert scalar(db_engine, "SELECT status FROM payments WHERE booking_id = :b", b=booking["id"]) == "confirmed"
