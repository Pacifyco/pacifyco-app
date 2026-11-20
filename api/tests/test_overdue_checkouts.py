# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Overdue check-outs and locked codes (CLAUDE.md 6.7; phase 8).

A booking still `in_progress` 30+ minutes past its end, or one whose codes got locked, needs an admin to
call both people and, if it stays stuck, close it by hand."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from tests.conftest import Mailbox
from tests.test_admin_payments import confirm, paid, verify_children  # noqa: F401
from tests.test_auto_cancel import move, status
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_cancellations import confirmed  # noqa: F401  (fixture)
from tests.test_documents import admin, as_user, client, parent, row, rows, scalar, storage  # noqa: F401
from tests.test_jobs import SECRET, bearer
from tests.test_jobs import client as jobs_client
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_payments import booking, pay  # noqa: F401  (fixture)
from tests.test_reports import admins_told  # noqa: F401  (fixture)
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import auth_for, user  # noqa: F401  (fixture)
from tests.test_sitter_bookings import set_status
from tests.test_verification import reviewer  # noqa: F401  (fixture)

ADMINS = "ops@example.com, founders@example.com"


def lock(db_engine, booking_id):
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE bookings SET codes_locked = true WHERE id = :b"), {"b": booking_id})


def set_in_progress(db_engine, booking_id, checked_in_at=None):
    """`in_progress` always means she checked in (the real flow sets both together)."""
    set_status(db_engine, booking_id, "in_progress")
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE bookings SET checked_in_at = :t WHERE id = :b"),
            {"t": checked_in_at or datetime.now(UTC), "b": booking_id},
        )


def to(mailbox, address):
    return [email for email in mailbox.sent if email.to == address]


def run_job(db_engine, mailbox, admins=ADMINS):
    response = jobs_client(db_engine, mailbox=mailbox, admin_alert_emails=admins).post(
        "/internal/jobs/frequent", headers=bearer(SECRET)
    )
    assert response.status_code == 200, response.text


def overdue_alerts(mailbox):
    return [email for email in mailbox.sent if email.button_label == "Open the admin panel"]


def needing_attention(client, admin_):
    return client.get("/admin/overdue-checkouts", headers=as_user(admin_))


def close(client, admin_, booking_id, reason="Called both; the booking went fine, she forgot to check out."):
    return client.post(f"/admin/bookings/{booking_id}/close", json={"reason": reason}, headers=as_user(admin_))


# ---------- the frequent job's email alert (6.7) ----------


def test_an_overdue_checkout_is_alerted_once(db_engine, confirmed):
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(hours=2, minutes=35))  # ends 35 min ago
    set_in_progress(db_engine, confirmed["id"])
    mailbox = Mailbox()
    run_job(db_engine, mailbox)
    sent = overdue_alerts(mailbox)
    assert sorted(email.to for email in sent) == ["founders@example.com", "ops@example.com"]
    assert sent[0].heading == "A check-out is overdue."
    assert (
        scalar(
            db_engine,
            "SELECT count(*) FROM audit_log WHERE action = 'overdue_checkout_alerted' AND entity_id = :b",
            b=confirmed["id"],
        )
        == 1
    )
    again = Mailbox()
    run_job(db_engine, again)  # not sent twice
    assert overdue_alerts(again) == []


def test_not_yet_overdue_isnt_alerted(db_engine, confirmed):
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(hours=1))  # still under way
    set_in_progress(db_engine, confirmed["id"])
    mailbox = Mailbox()
    run_job(db_engine, mailbox)
    assert overdue_alerts(mailbox) == []


# ---------- the admin list (6.7) ----------


def test_overdue_and_locked_bookings_need_attention(client, reviewer, db_engine, confirmed):
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(hours=2, minutes=35))
    set_in_progress(db_engine, confirmed["id"])
    response = needing_attention(client, reviewer)
    assert response.status_code == 200, response.text
    (item,) = [row_ for row_ in response.json() if row_["booking_id"] == confirmed["id"]]
    assert item["overdue"] is True
    assert item["parent_phone"] and item["sitter_phone"]


def test_a_locked_but_not_overdue_booking_needs_attention_too(client, reviewer, db_engine, confirmed):
    lock(db_engine, confirmed["id"])  # still "confirmed": she never managed to check in
    response = needing_attention(client, reviewer)
    (item,) = [row_ for row_ in response.json() if row_["booking_id"] == confirmed["id"]]
    assert item["overdue"] is False


def test_not_yet_overdue_and_not_locked_isnt_listed(client, reviewer, db_engine, confirmed):
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(minutes=10))
    set_in_progress(db_engine, confirmed["id"])
    response = needing_attention(client, reviewer)
    assert confirmed["id"] not in [row_["booking_id"] for row_ in response.json()]


def test_a_confirmed_booking_whose_time_passed_isnt_listed(client, reviewer, db_engine, confirmed):
    """Only an `in_progress` booking can be an overdue check-out; one still `confirmed` (never checked
    in, never locked) past its end isn't this feature's problem."""
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(hours=3))  # well past ends_at, still confirmed
    response = needing_attention(client, reviewer)
    assert confirmed["id"] not in [row_["booking_id"] for row_ in response.json()]


# ---------- closing by hand (6.7) ----------


def test_closing_needs_a_reason(client, reviewer, confirmed):
    response = close(client, reviewer, confirmed["id"], reason="   ")
    assert response.status_code == 422 and response.json()["error"]["code"] == "reason_needed"


def test_an_admin_closes_an_overdue_booking(client, reviewer, db_engine, confirmed):
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(hours=2, minutes=35))
    set_in_progress(db_engine, confirmed["id"])
    response = close(client, reviewer, confirmed["id"], reason="Called both; she forgot to check out.")
    assert response.status_code == 200, response.text
    assert status(db_engine, confirmed["id"]) == "closed_by_admin"
    saved = row(
        db_engine,
        "SELECT closed_by_admin_id, close_reason, checked_out_at FROM bookings WHERE id = :b",
        b=confirmed["id"],
    )
    assert str(saved["closed_by_admin_id"]) == str(reviewer)
    assert saved["close_reason"] == "Called both; she forgot to check out."
    assert saved["checked_out_at"] is not None
    audit_row = row(
        db_engine,
        "SELECT actor_id, before, after FROM audit_log WHERE action = 'booking_closed_by_admin' AND entity_id = :b",
        b=confirmed["id"],
    )
    assert str(audit_row["actor_id"]) == str(reviewer)
    assert audit_row["before"]["status"] == "in_progress" and audit_row["after"]["status"] == "closed_by_admin"
    assert confirmed["id"] not in [row_["booking_id"] for row_ in needing_attention(client, reviewer).json()]


def test_closing_doesnt_invent_a_checkout_time_if_she_never_checked_in(client, reviewer, db_engine, confirmed):
    """Locked on check-in, still `confirmed`: closing it mustn't set checked_out_at without checked_in_at
    (the database would refuse it)."""
    lock(db_engine, confirmed["id"])
    assert close(client, reviewer, confirmed["id"]).status_code == 200
    saved = row(db_engine, "SELECT checked_in_at, checked_out_at FROM bookings WHERE id = :b", b=confirmed["id"])
    assert saved["checked_in_at"] is None and saved["checked_out_at"] is None


def test_closing_keeps_her_real_checkin_time(client, reviewer, db_engine, confirmed):
    """If she did check in, the manual close shouldn't touch that timestamp."""
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(hours=2, minutes=35))
    checked_in_at = datetime.now(UTC) - timedelta(hours=1)
    set_in_progress(db_engine, confirmed["id"], checked_in_at)
    assert close(client, reviewer, confirmed["id"]).status_code == 200
    saved = row(db_engine, "SELECT checked_in_at, checked_out_at FROM bookings WHERE id = :b", b=confirmed["id"])
    assert abs((saved["checked_in_at"] - checked_in_at).total_seconds()) < 1
    assert saved["checked_out_at"] is not None


def test_cant_close_a_completed_or_cancelled_booking(client, reviewer, db_engine, confirmed):
    set_status(db_engine, confirmed["id"], "completed")
    response = close(client, reviewer, confirmed["id"])
    assert response.status_code == 409 and response.json()["error"]["code"] == "cannot_close"
