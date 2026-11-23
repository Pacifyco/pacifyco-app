# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""The admin dashboard (phase 10; Reuben, 2026-11-22): counts of what's waiting, each matching its queue,
and today's payouts (due now, overdue, paid today, India time). Counts only, for admins only."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from tests.test_admin_payments import confirm, paid, verify_children  # noqa: F401
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_cancellations import confirmed  # noqa: F401  (fixture)
from tests.test_documents import admin, as_user, client, parent, row, rows, scalar, storage  # noqa: F401
from tests.test_incidents import emergency
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_payments import booking  # noqa: F401  (fixture)
from tests.test_payouts import checked_out, due_ids, pay, upi_sitter
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, user  # noqa: F401  (fixture)
from tests.test_sitter_pay import HOUR
from tests.test_verification import reviewer  # noqa: F401  (fixture)


def dashboard(client, admin_id):
    response = client.get("/admin/dashboard", headers=as_user(admin_id))
    assert response.status_code == 200, response.text
    return response.json()


def test_each_count_matches_its_queue(client, db_engine, reviewer, confirmed):
    found = dashboard(client, reviewer)
    headers = as_user(reviewer)
    queue = client.get("/admin/verifications", headers=headers).json()
    assert found["sitters_to_review"] == len(queue["sitters"])
    assert found["families_to_review"] == len(queue["families"])
    money = client.get("/admin/payments", headers=headers).json()
    assert found["payments_to_check"] == len(money["to_check"])
    assert found["refunds_to_pay"] == len(money["refunds"])
    assert found["reports_open"] == len(client.get("/admin/reports", headers=headers).json())
    assert found["overdue_checkouts"] == len(client.get("/admin/overdue-checkouts", headers=headers).json())
    assert found["issues_open"] == len(client.get("/admin/issues", headers=headers).json())
    assert found["low_ratings"] == len(client.get("/admin/rating-flags", headers=headers).json())
    incidents = client.get("/admin/incidents", headers=headers).json()
    assert found["incidents_unresolved"] == len(incidents)
    assert found["incidents_open"] == len([item for item in incidents if item["status"] == "open"])


def test_an_emergency_counts_until_resolved(client, db_engine, reviewer, confirmed, finished_parent):
    before = dashboard(client, reviewer)
    with db_engine.begin() as conn:  # under way: started 5 minutes ago
        conn.execute(
            text("UPDATE bookings SET starts_at = :s, ends_at = :e WHERE id = :b"),
            {
                "s": datetime.now(UTC) - timedelta(minutes=5),
                "e": datetime.now(UTC) + timedelta(hours=2),
                "b": confirmed["id"],
            },
        )
    assert emergency(client, finished_parent, confirmed["id"], "emergency").status_code == 201
    after = dashboard(client, reviewer)
    assert after["incidents_open"] == before["incidents_open"] + 1
    assert after["incidents_unresolved"] == before["incidents_unresolved"] + 1


def test_payouts_due_overdue_and_paid_today(client, db_engine, reviewer, confirmed, finished_parent):
    before = dashboard(client, reviewer)
    checked_out(client, db_engine, confirmed, finished_parent)  # ₹600 booking pay and ₹300 overtime
    due = dashboard(client, reviewer)
    assert due["payouts_due"] == before["payouts_due"] + 2
    assert due["payouts_due_paise"] == before["payouts_due_paise"] + 3 * HOUR
    assert due["payouts_overdue"] == before["payouts_overdue"]

    with db_engine.begin() as conn:  # one of them past its 12 hours
        conn.execute(
            text(
                "UPDATE sitter_earnings SET due_by = now() - interval '1 minute'"
                " WHERE booking_id = :b AND kind = 'overtime'"
            ),
            {"b": confirmed["id"]},
        )
    assert dashboard(client, reviewer)["payouts_overdue"] == before["payouts_overdue"] + 1

    upi_sitter(db_engine, confirmed)
    assert pay(client, reviewer, confirmed, due_ids(client, reviewer, confirmed), "123456789012").status_code == 200
    after = dashboard(client, reviewer)
    assert after["payouts_due"] == before["payouts_due"]
    assert after["paid_today"] == before["paid_today"] + 1
    assert after["paid_today_paise"] == before["paid_today_paise"] + 3 * HOUR


def test_counts_only_and_admins_only(client, reviewer, finished_parent):
    found = dashboard(client, reviewer)
    assert all(isinstance(value, int) for value in found.values())  # no names, no bank details
    assert client.get("/admin/dashboard", headers=auth_for(finished_parent)).status_code == 403
