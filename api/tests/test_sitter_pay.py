# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Sitter pay (CLAUDE.md 6.2, 6.5, 6.8, 6.10; phase 9; Reuben, 2026-11-22).

Level pay x hours worked (check-in to the booked end, whatever the number of children), plus overtime;
fees from confirmed reports; held until the booking has ended with no overtime request waiting and no
open incident, then due within 12 hours. The booking here is a 2-hour Unwind booking: ₹300 an hour.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from tests.test_admin_payments import confirm, paid, verify_children  # noqa: F401
from tests.test_auto_cancel import move
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_cancellations import confirmed  # noqa: F401  (fixture)
from tests.test_checkin import do_check_out, out_code
from tests.test_documents import admin, as_user, client, parent, row, rows, scalar, storage  # noqa: F401
from tests.test_incidents import emergency, incident_id
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_overdue_checkouts import set_in_progress
from tests.test_payments import booking  # noqa: F401  (fixture)
from tests.test_reports import decide, man_home, not_home, report_id, reported_minutes_ago, under_age, unsafe
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, user  # noqa: F401  (fixture)
from tests.test_sitter_bookings import signed_in
from tests.test_verification import reviewer  # noqa: F401  (fixture)

HOUR = 30_000  # Unwind level pay, in paise


def earnings(db_engine, booking_id):
    return {
        item["kind"]: item
        for item in rows(
            db_engine,
            "SELECT kind, amount_paise, minutes, status, released_at, due_by"
            " FROM sitter_earnings WHERE booking_id = :b",
            b=booking_id,
        )
    }


def started(db_engine, booking_id, minutes_ago, *, checked_in_after=0, hours=2):
    """Moves the booking to have started `minutes_ago`, checked in `checked_in_after` minutes after the start."""
    start = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    move(db_engine, booking_id, start, hours=hours)
    set_in_progress(db_engine, booking_id, checked_in_at=start + timedelta(minutes=checked_in_after))


def check_out(client, db_engine, booking_id, finished_parent):
    sitter = signed_in(db_engine, scalar(db_engine, "SELECT sitter_id FROM bookings WHERE id = :b", b=booking_id))
    code = out_code(client, finished_parent, booking_id).json()["code"]
    response = do_check_out(client, sitter, booking_id, code=code)
    assert response.status_code == 200, response.text
    return sitter


def assert_due_in_12_hours(earning):
    assert earning["status"] == "released"
    assert earning["due_by"] - earning["released_at"] == timedelta(hours=12)
    assert abs(earning["released_at"] - datetime.now(UTC)) < timedelta(minutes=2)


# ---------- check-out (6.2, 6.8) ----------


def test_paid_for_the_booked_hours_even_if_she_checks_out_early(client, db_engine, confirmed, finished_parent):
    started(db_engine, confirmed["id"], 60)  # checked in at the start, out an hour before the end
    check_out(client, db_engine, confirmed["id"], finished_parent)
    found = earnings(db_engine, confirmed["id"])
    assert set(found) == {"booking"}
    assert found["booking"]["amount_paise"] == 2 * HOUR and found["booking"]["minutes"] == 120
    assert_due_in_12_hours(found["booking"])
    audit = [r["action"] for r in rows(db_engine, "SELECT action FROM audit_log WHERE entity = 'sitter_earning'")]
    assert "earning_recorded" in audit and "earning_released" in audit


def test_a_late_check_in_is_paid_from_check_in_whatever_the_number_of_children(
    client, db_engine, confirmed, finished_parent
):
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE bookings SET children_count = 3 WHERE id = :b"), {"b": confirmed["id"]})
    started(db_engine, confirmed["id"], 60, checked_in_after=30)
    check_out(client, db_engine, confirmed["id"], finished_parent)
    found = earnings(db_engine, confirmed["id"])["booking"]
    assert found["minutes"] == 90 and found["amount_paise"] == HOUR * 3 // 2  # ₹450: 1 h 30 min at ₹300


def test_overtime_is_paid_for_the_same_rounded_up_hours(client, db_engine, confirmed, finished_parent):
    started(db_engine, confirmed["id"], 140)  # the 2 hours ended 20 minutes ago
    check_out(client, db_engine, confirmed["id"], finished_parent)
    found = earnings(db_engine, confirmed["id"])
    assert found["booking"]["amount_paise"] == 2 * HOUR
    assert found["overtime"]["amount_paise"] == HOUR and found["overtime"]["minutes"] == 60
    assert_due_in_12_hours(found["overtime"])


def test_held_until_she_answers_an_overtime_request(client, db_engine, confirmed, finished_parent):
    started(db_engine, confirmed["id"], 60)
    asked = client.post(
        f"/parent/bookings/{confirmed['id']}/overtime", json={"hours": 1}, headers=auth_for(finished_parent)
    )
    assert asked.status_code == 201, asked.text
    sitter = check_out(client, db_engine, confirmed["id"], finished_parent)
    found = earnings(db_engine, confirmed["id"])["booking"]
    assert found["status"] == "held" and found["due_by"] is None

    answered = client.post(
        f"/sitter/overtime-requests/{asked.json()['overtime']['id']}/accept", headers=auth_for(sitter)
    )
    assert answered.status_code == 200, answered.text
    assert_due_in_12_hours(earnings(db_engine, confirmed["id"])["booking"])


def test_an_open_incident_holds_it_and_resolving_releases_it(client, db_engine, reviewer, confirmed, finished_parent):
    started(db_engine, confirmed["id"], 60)
    check_out(client, db_engine, confirmed["id"], finished_parent)
    assert earnings(db_engine, confirmed["id"])["booking"]["status"] == "released"

    # Raised in the hour after check-out: held again.
    assert emergency(client, finished_parent, confirmed["id"], "emergency").status_code == 201
    found = earnings(db_engine, confirmed["id"])["booking"]
    assert found["status"] == "held" and found["due_by"] is None

    rid = incident_id(db_engine, confirmed["id"])
    resolved = client.post(f"/admin/incidents/{rid}/resolve", json={"note": "All fine"}, headers=as_user(reviewer))
    assert resolved.status_code == 200, resolved.text
    assert_due_in_12_hours(earnings(db_engine, confirmed["id"])["booking"])


# ---------- an admin's manual close (6.7) ----------


def close(client, admin_id, booking_id, **body):
    return client.post(
        f"/admin/bookings/{booking_id}/close", json={"reason": "Called both", **body}, headers=as_user(admin_id)
    )


def test_a_manual_close_pays_hours_worked_if_she_checked_in(client, db_engine, reviewer, confirmed):
    started(db_engine, confirmed["id"], 160, checked_in_after=15)
    response = close(client, reviewer, confirmed["id"])
    assert response.status_code == 200 and response.json()["checked_in"] is True
    found = earnings(db_engine, confirmed["id"])
    assert set(found) == {"booking"} and found["booking"]["minutes"] == 105
    assert_due_in_12_hours(found["booking"])
    refused = close(client, reviewer, confirmed["id"], pay_hours=1)  # already closed, and she checked in
    assert refused.status_code in (409, 422)


def test_she_checked_in_so_the_admin_cant_choose_her_hours(client, db_engine, reviewer, confirmed):
    started(db_engine, confirmed["id"], 160)
    response = close(client, reviewer, confirmed["id"], pay_hours=1)
    assert response.status_code == 422 and response.json()["error"]["code"] == "pay_hours_not_needed"


def never_checked_in(db_engine, booking_id):
    """Confirmed, started 3 hours ago, no check-in (say, the codes got locked)."""
    move(db_engine, booking_id, datetime.now(UTC) - timedelta(hours=3))
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE bookings SET codes_locked = true WHERE id = :b"), {"b": booking_id})


def test_never_checked_in_nothing_unless_the_admin_chooses_hours(client, db_engine, reviewer, confirmed):
    never_checked_in(db_engine, confirmed["id"])
    assert close(client, reviewer, confirmed["id"], pay_hours=3).json()["error"]["code"] == "invalid_pay_hours"
    response = close(client, reviewer, confirmed["id"], pay_hours=1)
    assert response.status_code == 200, response.text
    found = earnings(db_engine, confirmed["id"])["booking"]
    assert found["amount_paise"] == HOUR and found["minutes"] == 60
    assert_due_in_12_hours(found)


def test_never_checked_in_and_no_hours_chosen_she_earns_nothing(client, db_engine, reviewer, confirmed):
    never_checked_in(db_engine, confirmed["id"])
    assert close(client, reviewer, confirmed["id"]).status_code == 200
    assert earnings(db_engine, confirmed["id"]) == {}


# ---------- confirmed reports (6.5) ----------


@pytest.fixture
def under_way(db_engine, confirmed):
    """Started 5 minutes ago, not checked in."""
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(minutes=5))
    return confirmed


def sitter_of(db_engine, booking_id):
    return signed_in(db_engine, scalar(db_engine, "SELECT sitter_id FROM bookings WHERE id = :b", b=booking_id))


def test_no_one_home_the_show_up_fee_is_100_per_booked_hour(client, db_engine, reviewer, under_way):
    assert not_home(client, sitter_of(db_engine, under_way["id"]), under_way["id"]).status_code == 201
    reported_minutes_ago(db_engine, under_way["id"], 21)
    assert decide(client, reviewer, report_id(db_engine, under_way["id"]), "confirm").status_code == 200
    found = earnings(db_engine, under_way["id"])
    assert set(found) == {"show_up_fee"} and found["show_up_fee"]["amount_paise"] == 2 * 10_000
    assert_due_in_12_hours(found["show_up_fee"])  # 12 hours from the admin's decision


def test_only_a_man_home_a_flat_100(client, db_engine, reviewer, under_way):
    assert man_home(client, sitter_of(db_engine, under_way["id"]), under_way["id"]).status_code == 201
    assert decide(client, reviewer, report_id(db_engine, under_way["id"]), "confirm").status_code == 200
    assert earnings(db_engine, under_way["id"])["show_up_fee"]["amount_paise"] == 10_000


def test_a_child_under_18_months_her_level_pay_for_1_hour(client, db_engine, reviewer, under_way):
    assert under_age(client, sitter_of(db_engine, under_way["id"]), under_way["id"]).status_code == 201
    assert decide(client, reviewer, report_id(db_engine, under_way["id"]), "confirm").status_code == 200
    found = earnings(db_engine, under_way["id"])["booking"]
    assert found["amount_paise"] == HOUR and found["minutes"] == 60


def test_unsafe_paid_from_check_in_until_she_reported_rounded_up(client, db_engine, reviewer, confirmed):
    started(db_engine, confirmed["id"], 40)  # checked in 40 minutes ago
    assert unsafe(client, sitter_of(db_engine, confirmed["id"]), confirmed["id"]).status_code == 201
    reported_minutes_ago(db_engine, confirmed["id"], 10)  # 30 minutes after check-in: 1 hour
    assert decide(client, reviewer, report_id(db_engine, confirmed["id"]), "confirm").status_code == 200
    found = earnings(db_engine, confirmed["id"])["booking"]
    assert found["amount_paise"] == HOUR and found["minutes"] == 60
    assert_due_in_12_hours(found)


def test_a_no_show_or_a_dismissed_report_earns_nothing(client, db_engine, reviewer, under_way, finished_parent):
    assert man_home(client, sitter_of(db_engine, under_way["id"]), under_way["id"]).status_code == 201
    assert decide(client, reviewer, report_id(db_engine, under_way["id"]), "dismiss", "Not so").status_code == 200
    assert earnings(db_engine, under_way["id"]) == {}
