# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Check-in and check-out codes (CLAUDE.md 6.7; phase 8).

A code is generated the first time it's asked for (encrypted at rest) and the same one is returned every
time after. The sitter enters it, with her location if she allows it; five wrong ones locks the booking's
codes and alerts admins."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from tests.test_admin_payments import confirm, paid, verify_children  # noqa: F401
from tests.test_auto_cancel import move, status
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_cancellations import confirmed  # noqa: F401  (fixture)
from tests.test_documents import admin, cleanup_documents, client, parent, row, rows, scalar, storage  # noqa: F401
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_payments import booking, pay  # noqa: F401  (fixture)
from tests.test_reports import admins_told  # noqa: F401  (fixture)
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, user  # noqa: F401  (fixture)
from tests.test_sitter_bookings import signed_in
from tests.test_verification import reviewer  # noqa: F401  (fixture)


@pytest.fixture
def under_way(db_engine, confirmed):
    """The confirmed booking, started 5 minutes ago (2 hours long)."""
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(minutes=5))
    return confirmed


def to(mailbox, address):
    return [email for email in mailbox.sent if email.to == address]


def in_code(client, who, booking_id):
    return client.get(f"/parent/bookings/{booking_id}/check-in-code", headers=auth_for(who))


def out_code(client, who, booking_id):
    return client.get(f"/parent/bookings/{booking_id}/check-out-code", headers=auth_for(who))


def do_check_in(client, who, booking_id, code="0000", lat=12.9, lng=77.6):
    return client.post(
        f"/sitter/bookings/{booking_id}/check-in", json={"code": code, "lat": lat, "lng": lng}, headers=auth_for(who)
    )


def do_check_out(client, who, booking_id, code="0000", lat=12.9, lng=77.6):
    return client.post(
        f"/sitter/bookings/{booking_id}/check-out", json={"code": code, "lat": lat, "lng": lng}, headers=auth_for(who)
    )


# ---------- the check-in code (6.7) ----------


def test_not_shown_until_the_day_of_the_booking(client, confirmed, finished_parent):
    response = in_code(client, finished_parent, confirmed["id"])
    assert response.status_code == 409 and response.json()["error"]["code"] == "too_early"


def test_shown_once_confirmed_on_the_day_same_code_each_time(client, under_way, finished_parent):
    first = in_code(client, finished_parent, under_way["id"])
    assert first.status_code == 200, first.text
    code = first.json()["code"]
    assert len(code) == 4 and code.isdigit()
    second = in_code(client, finished_parent, under_way["id"])
    assert second.json()["code"] == code  # not regenerated


def test_another_parents_booking_is_not_found(client, db_engine, under_way):
    other = {"id": uuid.uuid4(), "email": f"{uuid.uuid4()}@example.com"}
    try:
        assert client.post("/me/profile", json=PARENT, headers=auth_for(other)).status_code == 201
        response = in_code(client, other, under_way["id"])
        assert response.status_code == 404
    finally:
        cleanup_documents(db_engine, other["id"])


# ---------- checking in (6.7) ----------


def test_wrong_code_counts_down_then_locks_and_alerts_admins(
    client, admins_told, db_engine, mailbox, under_way, finished_parent
):
    sitter = signed_in(db_engine, under_way["sitter_id"])
    real_code = in_code(client, finished_parent, under_way["id"]).json()["code"]
    wrong_code = "0000" if real_code != "0000" else "1111"
    for left in (4, 3, 2, 1):
        wrong = do_check_in(client, sitter, under_way["id"], code=wrong_code)
        assert wrong.status_code == 409, wrong.text
        assert wrong.json()["error"]["code"] == "wrong_code"
        assert wrong.json()["error"]["details"]["attempts_left"] == left
    locked = do_check_in(client, sitter, under_way["id"], code=wrong_code)
    assert locked.status_code == 409 and locked.json()["error"]["code"] == "codes_locked"
    assert scalar(db_engine, "SELECT codes_locked FROM bookings WHERE id = :b", b=under_way["id"]) is True
    assert "locked" in to(mailbox, "ops@example.com")[-1].subject.lower()
    still_locked = do_check_in(client, sitter, under_way["id"], code=real_code)  # even the real code, now
    assert still_locked.status_code == 409 and still_locked.json()["error"]["code"] == "codes_locked"


def test_checking_in_with_the_right_code_records_her_location(client, db_engine, under_way, finished_parent):
    sitter = signed_in(db_engine, under_way["sitter_id"])
    code = in_code(client, finished_parent, under_way["id"]).json()["code"]
    response = do_check_in(client, sitter, under_way["id"], code=code, lat=12.97, lng=77.59)
    assert response.status_code == 200, response.text
    assert status(db_engine, under_way["id"]) == "in_progress"
    row_ = row(
        db_engine, "SELECT checked_in_at, check_in_lat, check_in_lng FROM bookings WHERE id = :b", b=under_way["id"]
    )
    assert row_["checked_in_at"] is not None and row_["check_in_lat"] == 12.97 and row_["check_in_lng"] == 77.59


def test_denied_location_still_checks_her_in(client, db_engine, under_way, finished_parent):
    sitter = signed_in(db_engine, under_way["sitter_id"])
    code = in_code(client, finished_parent, under_way["id"]).json()["code"]
    response = do_check_in(client, sitter, under_way["id"], code=code, lat=None, lng=None)
    assert response.status_code == 200, response.text
    row_ = row(db_engine, "SELECT checked_in_at, check_in_lat FROM bookings WHERE id = :b", b=under_way["id"])
    assert row_["checked_in_at"] is not None and row_["check_in_lat"] is None


def test_cant_check_in_twice(client, db_engine, under_way, finished_parent):
    sitter = signed_in(db_engine, under_way["sitter_id"])
    code = in_code(client, finished_parent, under_way["id"]).json()["code"]
    assert do_check_in(client, sitter, under_way["id"], code=code).status_code == 200
    again = do_check_in(client, sitter, under_way["id"], code=code)
    assert again.status_code == 409 and again.json()["error"]["code"] == "not_now"


def test_cant_check_in_days_before_the_booking(client, db_engine, confirmed):
    """No code exists yet (the parent can't see it either, 6.7), so any code is wrong."""
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    response = do_check_in(client, sitter, confirmed["id"], code="0000")
    assert response.status_code == 409 and response.json()["error"]["code"] == "wrong_code"
    assert status(db_engine, confirmed["id"]) == "confirmed"


def test_a_malformed_code_is_rejected(client, db_engine, under_way):
    sitter = signed_in(db_engine, under_way["sitter_id"])
    response = do_check_in(client, sitter, under_way["id"], code="12")
    assert response.status_code == 422


# ---------- the check-out code and checking out (6.7) ----------


def test_check_out_code_only_once_checked_in(client, under_way, finished_parent):
    response = out_code(client, finished_parent, under_way["id"])
    assert response.status_code == 409 and response.json()["error"]["code"] == "not_now"


def test_checking_out_completes_the_booking(client, db_engine, under_way, finished_parent):
    sitter = signed_in(db_engine, under_way["sitter_id"])
    in_code_value = in_code(client, finished_parent, under_way["id"]).json()["code"]
    assert do_check_in(client, sitter, under_way["id"], code=in_code_value).status_code == 200

    out_code_value = out_code(client, finished_parent, under_way["id"]).json()["code"]
    response = do_check_out(client, sitter, under_way["id"], code=out_code_value, lat=12.8, lng=77.5)
    assert response.status_code == 200, response.text
    assert status(db_engine, under_way["id"]) == "completed"
    row_ = row(
        db_engine, "SELECT checked_out_at, check_out_lat, check_out_lng FROM bookings WHERE id = :b", b=under_way["id"]
    )
    assert row_["checked_out_at"] is not None and row_["check_out_lat"] == 12.8


def test_the_check_in_code_doesnt_check_her_out(client, db_engine, under_way, finished_parent):
    sitter = signed_in(db_engine, under_way["sitter_id"])
    in_code_value = in_code(client, finished_parent, under_way["id"]).json()["code"]
    assert do_check_in(client, sitter, under_way["id"], code=in_code_value).status_code == 200
    wrong = do_check_out(client, sitter, under_way["id"], code=in_code_value)
    assert wrong.status_code == 409 and wrong.json()["error"]["code"] == "wrong_code"
