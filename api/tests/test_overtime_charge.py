# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Overtime at check-out (CLAUDE.md 6.8; phase 8).

Worked out at check-out, whether or not a request was ever made or accepted: checked-out time past the
booked end is rounded up to the full hour and charged, at the plan's price or the next tier's for hours
past the plan's own latest end; she's paid her own level pay for the same hours either way. Its payment
and the "unpaid overtime blocks new bookings" rule reuse the generic charge machinery, already covered in
`test_charges.py` and `test_payment_history.py` -- this file covers the computation itself and its wiring
into check-out."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import Booking
from app.services import overtime
from app.services.availability import INDIA
from tests.test_admin_payments import confirm, paid, verify_children  # noqa: F401
from tests.test_auto_cancel import move  # noqa: F401
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_cancellations import confirmed  # noqa: F401  (fixture)
from tests.test_checkin import do_check_out, out_code  # noqa: F401
from tests.test_documents import admin, client, parent, row, scalar, storage  # noqa: F401  (fixtures)
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_overdue_checkouts import set_in_progress  # noqa: F401
from tests.test_payments import booking, pay  # noqa: F401  (fixture)
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, user  # noqa: F401  (fixture)
from tests.test_sitter_bookings import signed_in
from tests.test_verification import reviewer  # noqa: F401  (fixture)


def to(mailbox, address):
    return [email for email in mailbox.sent if email.to == address]


def put_booking(db_engine, booking_id, *, plan, starts_at, ends_at, checked_out_at, children_count=1):
    """Crafts a finished booking's times and plan directly, to test the charge computation on exact,
    non-flaky boundaries (rather than depending on the real wall clock)."""
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE bookings SET plan = :plan, starts_at = :s, ends_at = :e, checked_in_at = :s, "
                "checked_out_at = :co, children_count = :c, status = 'completed' WHERE id = :b"
            ),
            {"plan": plan, "s": starts_at, "e": ends_at, "co": checked_out_at, "c": children_count, "b": booking_id},
        )


def charge_for(db_engine, booking_id, now) -> dict | None:
    """Runs the computation directly and reads the result back into plain values before the session
    (and its expired ORM attributes) closes."""
    with Session(db_engine) as db:
        charged = overtime.charge_for_checkout(db, db.get(Booking, booking_id), now)
        if charged is None:
            db.commit()
            return None
        result = {
            "hours_charged": charged.charge.hours_charged,
            "minutes_over": charged.charge.minutes_over,
            "amount_paise": charged.charge.amount_paise,
            "sitter_pay_paise": charged.charge.sitter_pay_paise,
            "payment_amount_paise": charged.payment.amount_paise,
            "payment_status": charged.payment.status.value,
            "payment_due_by": charged.payment.due_by,
        }
        db.commit()
        return result


# ---------- the computation itself (6.8) ----------


def test_nothing_charged_if_she_checks_out_on_time(db_engine, confirmed):
    starts = datetime(2026, 11, 25, 8, 0, tzinfo=INDIA)
    ends = starts + timedelta(hours=2)
    put_booking(db_engine, confirmed["id"], plan="pause", starts_at=starts, ends_at=ends, checked_out_at=ends)
    assert charge_for(db_engine, confirmed["id"], ends) is None
    assert scalar(db_engine, "SELECT count(*) FROM overtime_charges WHERE booking_id = :b", b=confirmed["id"]) == 0


def test_even_a_few_seconds_over_rounds_up_to_a_full_hour(db_engine, confirmed):
    starts = datetime(2026, 11, 25, 8, 0, tzinfo=INDIA)
    ends = starts + timedelta(hours=2)
    checked_out = ends + timedelta(seconds=5)
    put_booking(db_engine, confirmed["id"], plan="pause", starts_at=starts, ends_at=ends, checked_out_at=checked_out)
    result = charge_for(db_engine, confirmed["id"], checked_out)
    assert result["hours_charged"] == 1
    assert result["minutes_over"] == 0  # under a whole minute, but still a full hour's overtime
    assert result["amount_paise"] == 49_900  # Pause rate, well inside its 6pm latest end
    assert result["sitter_pay_paise"] == 20_000  # her own level pay for that hour
    assert result["payment_amount_paise"] == 49_900
    assert result["payment_status"] == "pending"
    assert result["payment_due_by"] == checked_out + timedelta(hours=2)  # 6.8: payable within 2 hours


def test_rounds_up_whole_hours_already_past_the_minute(db_engine, confirmed):
    starts = datetime(2026, 11, 25, 8, 0, tzinfo=INDIA)
    ends = starts + timedelta(hours=1)
    checked_out = ends + timedelta(hours=1, minutes=40)
    put_booking(db_engine, confirmed["id"], plan="pause", starts_at=starts, ends_at=ends, checked_out_at=checked_out)
    result = charge_for(db_engine, confirmed["id"], checked_out)
    assert result["hours_charged"] == 2  # 1h40m over rounds up to 2 full hours
    assert result["minutes_over"] == 100
    assert result["amount_paise"] == 49_900 * 2
    assert result["sitter_pay_paise"] == 20_000 * 2


def test_overage_past_the_plans_latest_end_is_charged_at_the_next_tier(db_engine, confirmed):
    """Unwind's latest end is 10:30pm (CLAUDE.md 6.1): the first overage hour (9-10pm) is still hers, the
    second (10-11pm) falls past it and is charged at Recharge's rate; she's still paid her own (Unwind)
    level pay for both hours (6.8)."""
    starts = datetime(2026, 11, 25, 19, 0, tzinfo=INDIA)  # 7 pm
    ends = starts + timedelta(hours=2)  # 9 pm
    checked_out = ends + timedelta(hours=2)  # 11 pm
    put_booking(db_engine, confirmed["id"], plan="unwind", starts_at=starts, ends_at=ends, checked_out_at=checked_out)
    result = charge_for(db_engine, confirmed["id"], checked_out)
    assert result["hours_charged"] == 2
    assert result["amount_paise"] == 69_900 + 89_900  # her own rate, then the next tier's
    assert result["sitter_pay_paise"] == 30_000 * 2  # her own level pay either way


def test_recharge_has_no_higher_tier(db_engine, confirmed):
    """Deferred default, decided 2026-11-03: overage past midnight on Recharge stays at the Recharge
    rate, since it has no higher tier to move to."""
    starts = datetime(2026, 11, 25, 23, 0, tzinfo=INDIA)  # 11 pm
    ends = starts + timedelta(hours=1)  # midnight
    checked_out = ends + timedelta(hours=1)  # 1 am
    put_booking(db_engine, confirmed["id"], plan="recharge", starts_at=starts, ends_at=ends, checked_out_at=checked_out)
    result = charge_for(db_engine, confirmed["id"], checked_out)
    assert result["amount_paise"] == 89_900
    assert result["sitter_pay_paise"] == 40_000


def test_the_same_booking_is_only_charged_once(db_engine, confirmed):
    starts = datetime(2026, 11, 25, 8, 0, tzinfo=INDIA)
    ends = starts + timedelta(hours=2)
    checked_out = ends + timedelta(hours=1)
    put_booking(db_engine, confirmed["id"], plan="pause", starts_at=starts, ends_at=ends, checked_out_at=checked_out)
    assert charge_for(db_engine, confirmed["id"], checked_out) is not None
    with Session(db_engine) as db:
        try:
            overtime.charge_for_checkout(db, db.get(Booking, confirmed["id"]), checked_out)
            db.commit()
            raised = False
        except Exception:
            db.rollback()
            raised = True
    assert raised  # the unique index on booking_id refuses a second row


# ---------- wiring into check-out (6.7/6.8) ----------


def test_checking_out_late_charges_overtime_and_emails_the_parent(
    client, db_engine, mailbox, confirmed, finished_parent
):
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(hours=1, minutes=20), hours=1)
    set_in_progress(db_engine, confirmed["id"])
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    out_code_value = out_code(client, finished_parent, confirmed["id"]).json()["code"]
    response = do_check_out(client, sitter, confirmed["id"], code=out_code_value)
    assert response.status_code == 200, response.text

    charge_row = row(db_engine, "SELECT * FROM overtime_charges WHERE booking_id = :b", b=confirmed["id"])
    assert charge_row["hours_charged"] >= 1
    payment_row = row(
        db_engine, "SELECT * FROM payments WHERE booking_id = :b AND kind = 'overtime'", b=confirmed["id"]
    )
    assert payment_row["status"] == "pending" and payment_row["due_by"] is not None
    assert payment_row["amount_paise"] == charge_row["amount_paise"]

    email = to(mailbox, finished_parent["email"])[-1]
    assert "overtime" in email.subject.lower()
    assert str(payment_row["id"]) in email.button_url


def test_checking_out_on_time_charges_nothing(client, db_engine, mailbox, confirmed, finished_parent):
    """Checked out before the booked end (an early check-out, 6.7): nothing is charged."""
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(minutes=5), hours=1)
    set_in_progress(db_engine, confirmed["id"])
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    out_code_value = out_code(client, finished_parent, confirmed["id"]).json()["code"]
    assert do_check_out(client, sitter, confirmed["id"], code=out_code_value).status_code == 200
    assert scalar(db_engine, "SELECT count(*) FROM overtime_charges WHERE booking_id = :b", b=confirmed["id"]) == 0
    assert not any("overtime" in email.subject.lower() for email in to(mailbox, finished_parent["email"]))


def test_admin_manual_close_doesnt_charge_overtime(db_engine, confirmed, admin):
    """A manual admin close (6.7) charges no overtime by itself (Reuben, 2026-11-21): there's no reliable
    "how late was she" once a call, not a code, ended the booking. The admin can choose to charge some
    (below)."""
    from app.services import checkin as checkin_service

    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(hours=2), hours=1)
    set_in_progress(db_engine, confirmed["id"])
    with Session(db_engine) as db:
        checkin_service.close_by_admin(db, admin, confirmed["id"], "No answer from either side.", datetime.now(UTC))
    assert scalar(db_engine, "SELECT count(*) FROM overtime_charges WHERE booking_id = :b", b=confirmed["id"]) == 0


def _close(client, admin_id, booking_id, **body):
    from tests.test_documents import as_user

    return client.post(
        f"/admin/bookings/{booking_id}/close", json={"reason": "Called both", **body}, headers=as_user(admin_id)
    )


def test_the_admin_may_charge_overtime_when_closing(client, reviewer, db_engine, mailbox, confirmed, finished_parent):
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(hours=3), hours=2)  # ended an hour ago
    set_in_progress(db_engine, confirmed["id"])
    response = _close(client, reviewer, confirmed["id"], overtime_hours=2)
    assert response.status_code == 200, response.text
    charge = row(
        db_engine, "SELECT hours_charged, amount_paise FROM overtime_charges WHERE booking_id = :b", b=confirmed["id"]
    )
    assert charge["hours_charged"] == 2 and charge["amount_paise"] > 0
    payment = row(
        db_engine,
        "SELECT amount_paise, status, due_by FROM payments WHERE booking_id = :b AND kind = 'overtime'",
        b=confirmed["id"],
    )
    assert payment["amount_paise"] == charge["amount_paise"] and payment["status"] == "pending"
    assert payment["due_by"] is not None
    email = to(mailbox, finished_parent["email"])[-1]
    assert "2 hours of overtime" in email.heading
    audit = row(
        db_engine,
        "SELECT actor_id, after FROM audit_log WHERE action = 'overtime_charged' AND entity_id = :b",
        b=confirmed["id"],
    )
    assert audit["actor_id"] == reviewer and audit["after"]["source"] == "admin_close"


def test_closing_without_choosing_charges_nothing(client, reviewer, db_engine, mailbox, confirmed, finished_parent):
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(hours=3), hours=2)
    set_in_progress(db_engine, confirmed["id"])
    assert _close(client, reviewer, confirmed["id"]).status_code == 200
    assert scalar(db_engine, "SELECT count(*) FROM overtime_charges WHERE booking_id = :b", b=confirmed["id"]) == 0
    assert not any("overtime" in email.subject.lower() for email in to(mailbox, finished_parent["email"]))


def test_overtime_hours_on_close_are_checked(client, reviewer, db_engine, confirmed):
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(hours=3), hours=2)
    set_in_progress(db_engine, confirmed["id"])
    assert _close(client, reviewer, confirmed["id"], overtime_hours=0).status_code == 422
    assert _close(client, reviewer, confirmed["id"], overtime_hours=7).status_code == 422
    assert scalar(db_engine, "SELECT status FROM bookings WHERE id = :b", b=confirmed["id"]) == "in_progress"


def test_unpaid_overtime_blocks_new_bookings(client, db_engine, confirmed, finished_parent, free_sitter):
    """6.8: until it's paid, it's an outstanding amount and the parent can't make new bookings."""
    from tests.test_charges import can_book

    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(hours=1, minutes=20), hours=1)
    set_in_progress(db_engine, confirmed["id"])
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    out_code_value = out_code(client, finished_parent, confirmed["id"]).json()["code"]
    assert do_check_out(client, sitter, confirmed["id"], code=out_code_value).status_code == 200
    assert can_book(client, db_engine, finished_parent, free_sitter) == 409
