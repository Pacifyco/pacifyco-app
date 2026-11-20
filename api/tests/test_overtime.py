# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Overtime requests (CLAUDE.md 6.8; phase 8, decided 2026-11-12).

During the booking the parent asks for whole extra hours; the sitter accepts or declines once they've
agreed it between them. Nothing is charged here -- overtime is always worked out at check-out, whether or
not a request was ever made or accepted."""

import uuid

from tests.test_admin_payments import confirm, paid, verify_children  # noqa: F401
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_cancellations import confirmed  # noqa: F401  (fixture)
from tests.test_documents import admin, cleanup_documents, client, parent, row, rows, scalar, storage  # noqa: F401
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_overdue_checkouts import set_in_progress
from tests.test_payments import booking, pay  # noqa: F401  (fixture)
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, user  # noqa: F401  (fixture)
from tests.test_sitter_bookings import signed_in

ADMINS = "ops@example.com"


def to(mailbox, address):
    return [email for email in mailbox.sent if email.to == address]


def request_overtime(client, parent_, booking_id, hours=2):
    return client.post(f"/parent/bookings/{booking_id}/overtime", json={"hours": hours}, headers=auth_for(parent_))


def accept(client, sitter, request_id):
    return client.post(f"/sitter/overtime-requests/{request_id}/accept", headers=auth_for(sitter))


def decline(client, sitter, request_id):
    return client.post(f"/sitter/overtime-requests/{request_id}/decline", headers=auth_for(sitter))


def get_booking(client, parent_, booking_id):
    return client.get(f"/parent/bookings/{booking_id}", headers=auth_for(parent_))


def get_sitter_booking(client, sitter, booking_id):
    return client.get(f"/sitter/bookings/{booking_id}", headers=auth_for(sitter))


# ---------- requesting (6.8) ----------


def test_only_once_the_booking_has_started(client, confirmed, finished_parent):
    response = request_overtime(client, finished_parent, confirmed["id"])
    assert response.status_code == 409 and response.json()["error"]["code"] == "not_now"


def test_requesting_notifies_the_sitter_nothing_charged(client, db_engine, mailbox, confirmed, finished_parent):
    set_in_progress(db_engine, confirmed["id"])
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    response = request_overtime(client, finished_parent, confirmed["id"], hours=2)
    assert response.status_code == 201, response.text
    overtime = response.json()["overtime"]
    assert overtime["hours"] == 2 and overtime["status"] == "pending" and overtime["decided_at"] is None
    assert to(mailbox, sitter["email"])[-1].heading == "Meera's family has asked for 2 more hours."
    # Nothing beyond the booking payment the `confirmed` fixture already made: requesting charges nothing.
    assert (
        scalar(
            db_engine, "SELECT count(*) FROM payments WHERE booking_id = :b AND kind != 'booking'", b=confirmed["id"]
        )
        == 0
    )


def test_cant_request_again_while_one_is_pending(client, db_engine, confirmed, finished_parent):
    set_in_progress(db_engine, confirmed["id"])
    assert request_overtime(client, finished_parent, confirmed["id"]).status_code == 201
    again = request_overtime(client, finished_parent, confirmed["id"], hours=1)
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_requested"


def test_hours_must_be_a_sane_whole_number(client, db_engine, confirmed, finished_parent):
    set_in_progress(db_engine, confirmed["id"])
    assert request_overtime(client, finished_parent, confirmed["id"], hours=0).status_code == 422
    assert request_overtime(client, finished_parent, confirmed["id"], hours=25).status_code == 422


def test_another_parents_booking_is_not_found(client, db_engine, confirmed):
    set_in_progress(db_engine, confirmed["id"])
    other = {"id": uuid.uuid4(), "email": f"{uuid.uuid4()}@example.com"}
    try:
        assert client.post("/me/profile", json=PARENT, headers=auth_for(other)).status_code == 201
        response = request_overtime(client, other, confirmed["id"])
        assert response.status_code == 404
    finally:
        cleanup_documents(db_engine, other["id"])


# ---------- her answer (6.8) ----------


def test_she_accepts_nothing_charged(client, db_engine, mailbox, confirmed, finished_parent):
    set_in_progress(db_engine, confirmed["id"])
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    request_id = request_overtime(client, finished_parent, confirmed["id"], hours=3).json()["overtime"]["id"]
    response = accept(client, sitter, request_id)
    assert response.status_code == 200, response.text
    assert response.json()["overtime"]["status"] == "accepted"
    assert response.json()["overtime"]["decided_at"] is not None
    assert "can stay 3 more hours" in to(mailbox, finished_parent["email"])[-1].heading
    # Nothing beyond the booking payment the `confirmed` fixture already made: accepting charges nothing.
    assert (
        scalar(
            db_engine, "SELECT count(*) FROM payments WHERE booking_id = :b AND kind != 'booking'", b=confirmed["id"]
        )
        == 0
    )
    assert get_booking(client, finished_parent, confirmed["id"]).json()["overtime"]["status"] == "accepted"


def test_she_declines(client, db_engine, mailbox, confirmed, finished_parent):
    set_in_progress(db_engine, confirmed["id"])
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    request_id = request_overtime(client, finished_parent, confirmed["id"], hours=1).json()["overtime"]["id"]
    response = decline(client, sitter, request_id)
    assert response.status_code == 200, response.text
    assert response.json()["overtime"]["status"] == "declined"
    assert to(mailbox, finished_parent["email"])[-1].heading == "Lakshmi can't stay longer."


def test_she_can_only_decide_once(client, db_engine, confirmed, finished_parent):
    set_in_progress(db_engine, confirmed["id"])
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    request_id = request_overtime(client, finished_parent, confirmed["id"]).json()["overtime"]["id"]
    assert accept(client, sitter, request_id).status_code == 200
    again = accept(client, sitter, request_id)
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_decided"


def test_another_sitter_cant_decide(client, db_engine, confirmed, finished_parent, free_sitter):
    set_in_progress(db_engine, confirmed["id"])
    stranger = free_sitter("unwind")
    request_id = request_overtime(client, finished_parent, confirmed["id"]).json()["overtime"]["id"]
    assert accept(client, stranger, request_id).status_code == 404


def test_requesting_again_after_a_decision(client, db_engine, confirmed, finished_parent):
    set_in_progress(db_engine, confirmed["id"])
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    first = request_overtime(client, finished_parent, confirmed["id"], hours=1).json()["overtime"]["id"]
    assert decline(client, sitter, first).status_code == 200
    second = request_overtime(client, finished_parent, confirmed["id"], hours=2)
    assert second.status_code == 201, second.text
    assert second.json()["overtime"]["hours"] == 2


def test_sitter_sees_the_request_on_her_booking(client, db_engine, confirmed, finished_parent):
    set_in_progress(db_engine, confirmed["id"])
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    request_overtime(client, finished_parent, confirmed["id"], hours=1)
    detail = get_sitter_booking(client, sitter, confirmed["id"]).json()
    assert detail["overtime"]["hours"] == 1 and detail["overtime"]["status"] == "pending"
