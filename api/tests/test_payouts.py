# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""The admin payouts-due list (CLAUDE.md 6.10; phase 9; Reuben, 2026-11-22).

Released, unpaid earnings grouped by sitter (one transfer each), soonest deadline first, with her bank or
UPI details. Showing bank details writes an audit row every time; the banner's counts show and log nothing.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import sitters as sitters_service
from tests.test_admin_payments import confirm, paid, verify_children  # noqa: F401
from tests.test_auth import TEST_FIELD_ENCRYPTION_KEY
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_cancellations import confirmed  # noqa: F401  (fixture)
from tests.test_documents import admin, as_user, client, parent, row, rows, scalar, storage  # noqa: F401
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_payments import booking  # noqa: F401  (fixture)
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, user  # noqa: F401  (fixture)
from tests.test_sitter_pay import HOUR, check_out, started
from tests.test_verification import reviewer  # noqa: F401  (fixture)


def checked_out(client, db_engine, confirmed, finished_parent):
    started(db_engine, confirmed["id"], 140)  # ended 20 minutes ago: booking pay and 1 hour of overtime
    check_out(client, db_engine, confirmed["id"], finished_parent)
    return confirmed


def payouts(client, who):
    return client.get("/admin/payouts", headers=auth_for(who) if isinstance(who, dict) else as_user(who))


def ours(found, booking):
    return next(group for group in found if group["sitter_id"] == str(booking["sitter_id"]))


def test_whats_due_by_sitter_with_her_upi(client, db_engine, reviewer, confirmed, finished_parent):
    checked_out(client, db_engine, confirmed, finished_parent)
    with Session(db_engine) as db:
        sitters_service.set_payout_upi(db, confirmed["sitter_id"], "lakshmi@okaxis")
    response = payouts(client, reviewer)
    assert response.status_code == 200, response.text
    group = ours(response.json(), confirmed)
    assert group["payout_method"] == "upi" and group["upi_id"] == "lakshmi@okaxis" and group["bank"] is None
    assert group["total_paise"] == 3 * HOUR  # 2 hours, plus 1 hour of overtime
    assert [item["kind"] for item in group["earnings"]] == ["booking", "overtime"]
    assert all(item["booking_id"] == confirmed["id"] for item in group["earnings"])
    due_by = datetime.fromisoformat(group["next_due_by"])
    assert timedelta(hours=11, minutes=55) < due_by - datetime.now(UTC) <= timedelta(hours=12)
    # No bank details shown, so nothing logged.
    viewed = "SELECT count(*) FROM audit_log WHERE action = 'bank_details_viewed' AND entity_id = :s"
    assert scalar(db_engine, viewed, s=str(confirmed["sitter_id"])) == 0


def test_bank_details_are_shown_and_every_view_is_logged(client, db_engine, reviewer, confirmed, finished_parent):
    checked_out(client, db_engine, confirmed, finished_parent)
    with Session(db_engine) as db:
        sitters_service.set_payout_bank(
            db,
            confirmed["sitter_id"],
            sitters_service.BankDetails("Lakshmi Nair", "123456789012", "HDFC0001234"),
            TEST_FIELD_ENCRYPTION_KEY,
        )
    group = ours(payouts(client, reviewer).json(), confirmed)
    assert group["payout_method"] == "bank"
    assert group["bank"] == {
        "account_holder_name": "Lakshmi Nair",
        "account_number": "123456789012",
        "ifsc_code": "HDFC0001234",
    }
    payouts(client, reviewer)
    viewed = rows(
        db_engine,
        "SELECT actor_id FROM audit_log WHERE action = 'bank_details_viewed' AND entity_id = :s",
        s=str(confirmed["sitter_id"]),
    )
    assert [item["actor_id"] for item in viewed] == [reviewer, reviewer]


def test_soonest_deadline_first_and_held_or_paid_earnings_left_out(
    client, db_engine, reviewer, confirmed, finished_parent
):
    checked_out(client, db_engine, confirmed, finished_parent)
    upi_sitter(db_engine, confirmed)
    overtime = next(
        item["id"]
        for item in ours(payouts(client, reviewer).json(), confirmed)["earnings"]
        if item["kind"] == "overtime"
    )
    assert pay(client, reviewer, confirmed, [overtime]).status_code == 200  # her overtime is already paid
    with db_engine.begin() as conn:  # her booking pay is due sooner than everyone else's
        conn.execute(
            text(
                "UPDATE sitter_earnings SET due_by = now() - interval '1 hour'"
                " WHERE booking_id = :b AND status = 'released'"
            ),
            {"b": confirmed["id"]},
        )
    found = payouts(client, reviewer).json()
    assert found[0]["sitter_id"] == str(confirmed["sitter_id"])  # overdue: first
    assert [item["kind"] for item in found[0]["earnings"]] == ["booking"]
    summary = client.get("/admin/payouts/summary", headers=as_user(reviewer)).json()
    assert summary["due"] >= 1 and summary["overdue"] >= 1


def test_the_summary_counts_and_logs_nothing(client, db_engine, reviewer, confirmed, finished_parent):
    before = scalar(db_engine, "SELECT count(*) FROM audit_log WHERE action = 'bank_details_viewed'")
    empty = client.get("/admin/payouts/summary", headers=as_user(reviewer)).json()
    checked_out(client, db_engine, confirmed, finished_parent)
    after = client.get("/admin/payouts/summary", headers=as_user(reviewer)).json()
    assert after["due"] == empty["due"] + 2 and after["overdue"] == empty["overdue"]
    assert scalar(db_engine, "SELECT count(*) FROM audit_log WHERE action = 'bank_details_viewed'") == before


def test_only_admins(client, confirmed, finished_parent, db_engine):
    from tests.test_sitter_bookings import signed_in

    sitter = signed_in(db_engine, confirmed["sitter_id"])
    for who in (finished_parent, sitter):
        assert payouts(client, who).status_code == 403
        assert client.get("/admin/payouts/summary", headers=auth_for(who)).status_code == 403


# ---------- marking it paid (6.10) ----------


def upi_sitter(db_engine, booking):
    with Session(db_engine) as db:
        sitters_service.set_payout_upi(db, booking["sitter_id"], "lakshmi@okaxis")


def pay(client, admin_id, booking, earning_ids, reference="123456789012"):
    return client.post(
        f"/admin/payouts/{booking['sitter_id']}/paid",
        json={"earning_ids": earning_ids, "transfer_reference": reference},
        headers=as_user(admin_id),
    )


def due_ids(client, reviewer, booking):
    return [item["id"] for item in ours(payouts(client, reviewer).json(), booking)["earnings"]]


def test_paid_in_one_transfer_and_she_is_told(client, db_engine, mailbox, reviewer, confirmed, finished_parent):
    checked_out(client, db_engine, confirmed, finished_parent)
    upi_sitter(db_engine, confirmed)
    ids = due_ids(client, reviewer, confirmed)
    response = pay(client, reviewer, confirmed, ids, " 123456789012 ")
    assert response.status_code == 200, response.text
    assert response.json()["amount_paise"] == 3 * HOUR and response.json()["method"] == "upi"
    payout = row(db_engine, "SELECT * FROM payouts WHERE id = :p", p=response.json()["id"])
    assert payout["transfer_reference"] == "123456789012" and payout["paid_by"] == reviewer
    paid_rows = rows(
        db_engine, "SELECT status, payout_id FROM sitter_earnings WHERE booking_id = :b", b=confirmed["id"]
    )
    assert all(item["status"] == "paid" and str(item["payout_id"]) == response.json()["id"] for item in paid_rows)
    assert not any(group["sitter_id"] == str(confirmed["sitter_id"]) for group in payouts(client, reviewer).json())
    told = [email for email in mailbox.sent if email.heading == "We've paid you ₹900."]
    assert len(told) == 1 and "by UPI" in told[0].body
    audit = row(
        db_engine,
        "SELECT actor_id, after FROM audit_log WHERE action = 'payout_paid' AND entity_id = :p",
        p=response.json()["id"],
    )
    assert audit["actor_id"] == reviewer and sorted(audit["after"]["earning_ids"]) == sorted(ids)


def test_what_was_shown_must_still_be_due(client, db_engine, reviewer, confirmed, finished_parent):
    checked_out(client, db_engine, confirmed, finished_parent)
    upi_sitter(db_engine, confirmed)
    ids = due_ids(client, reviewer, confirmed)
    assert pay(client, reviewer, confirmed, ids).status_code == 200
    again = pay(client, reviewer, confirmed, ids, "999988887777")  # already paid
    assert again.status_code == 409 and again.json()["error"]["code"] == "payout_changed"


def test_references_are_checked_and_used_once(client, db_engine, reviewer, confirmed, finished_parent):
    checked_out(client, db_engine, confirmed, finished_parent)
    upi_sitter(db_engine, confirmed)
    booking_pay, overtime = due_ids(client, reviewer, confirmed)
    bad = pay(client, reviewer, confirmed, [booking_pay], "12-34")
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_reference"
    assert pay(client, reviewer, confirmed, [booking_pay], "UTR0000111122").status_code == 200
    used = pay(client, reviewer, confirmed, [overtime], "utr0000111122")
    assert used.status_code == 409 and used.json()["error"]["code"] == "reference_used"


def test_no_payout_details_no_payout(client, db_engine, reviewer, confirmed, finished_parent):
    checked_out(client, db_engine, confirmed, finished_parent)
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE sitters SET payout_method = NULL WHERE profile_id = :s"), {"s": confirmed["sitter_id"]}
        )
    response = pay(client, reviewer, confirmed, due_ids(client, reviewer, confirmed))
    assert response.status_code == 409 and response.json()["error"]["code"] == "no_payout_details"


def test_only_admins_mark_paid(client, db_engine, confirmed, finished_parent):
    response = client.post(
        f"/admin/payouts/{confirmed['sitter_id']}/paid",
        json={"earning_ids": [str(confirmed["id"])], "transfer_reference": "123456789012"},
        headers=auth_for(finished_parent),
    )
    assert response.status_code == 403


# ---------- alerts: under 3 hours left, and overdue (6.10) ----------


def alerts(mailbox, subject_part):
    return [email for email in mailbox.sent if subject_part in email.subject]


def alerted(db_engine, action, booking):
    return scalar(
        db_engine,
        "SELECT count(*) FROM audit_log a JOIN sitter_earnings e ON a.entity_id = e.id::text"
        " WHERE a.action = :a AND e.booking_id = :b",
        a=action,
        b=booking["id"],
    )


def test_admins_are_told_once_with_3_hours_left_and_once_overdue(client, db_engine, confirmed, finished_parent):
    from tests.test_overdue_checkouts import Mailbox, run_job

    checked_out(client, db_engine, confirmed, finished_parent)
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE sitter_earnings SET due_by = now() + interval '2 hours' WHERE booking_id = :b"),
            {"b": confirmed["id"]},
        )
    first = Mailbox()
    run_job(db_engine, first)
    soon = alerts(first, "due within 3 hours")
    assert sorted(email.to for email in soon) == ["founders@example.com", "ops@example.com"]
    assert "Sitters must be paid within 12 hours" in soon[0].body
    assert alerted(db_engine, "payout_due_soon_alerted", confirmed) == 2  # both of her earnings
    again = Mailbox()
    run_job(db_engine, again)
    assert alerts(again, "due within 3 hours") == []  # not sent twice

    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE sitter_earnings SET due_by = now() - interval '5 minutes' WHERE booking_id = :b"),
            {"b": confirmed["id"]},
        )
    late = Mailbox()
    run_job(db_engine, late)
    assert len(alerts(late, "overdue")) == 2 and alerted(db_engine, "payout_overdue_alerted", confirmed) == 2
    last = Mailbox()
    run_job(db_engine, last)
    assert alerts(last, "payouts are overdue") == alerts(last, "payout is overdue") == []


def test_no_alert_with_plenty_of_time_left(client, db_engine, confirmed, finished_parent):
    from tests.test_overdue_checkouts import Mailbox, run_job

    checked_out(client, db_engine, confirmed, finished_parent)  # due in 12 hours
    run_job(db_engine, Mailbox())
    assert alerted(db_engine, "payout_due_soon_alerted", confirmed) == 0
    assert alerted(db_engine, "payout_overdue_alerted", confirmed) == 0


# ---------- her earnings dashboard (6.10) ----------


def her_earnings(client, db_engine, booking):
    from tests.test_sitter_bookings import signed_in

    sitter = signed_in(db_engine, booking["sitter_id"])
    return client.get("/sitter/earnings", headers=auth_for(sitter))


def test_she_sees_whats_held_due_and_paid(client, db_engine, reviewer, confirmed, finished_parent):
    checked_out(client, db_engine, confirmed, finished_parent)
    found = her_earnings(client, db_engine, confirmed).json()
    assert found["held_paise"] == 0 and found["due_paise"] == 3 * HOUR and found["paid_paise"] == 0
    assert [item["kind"] for item in found["earnings"]] == ["booking", "overtime"]
    first = found["earnings"][0]
    assert first["status"] == "released" and first["due_by"] is not None and first["paid_at"] is None
    assert first["family_name"] and first["minutes"] == 120 and first["booking_id"] == confirmed["id"]
    assert "price" not in str(found).lower() and "plan" not in str(found).lower()

    upi_sitter(db_engine, confirmed)
    assert pay(client, reviewer, confirmed, due_ids(client, reviewer, confirmed), "555566667777").status_code == 200
    paid = her_earnings(client, db_engine, confirmed).json()
    assert paid["due_paise"] == 0 and paid["paid_paise"] == 3 * HOUR
    assert all(item["status"] == "paid" and item["paid_at"] for item in paid["earnings"])
    (payout,) = paid["payouts"]
    assert payout["amount_paise"] == 3 * HOUR and payout["method"] == "upi"
    assert payout["transfer_reference"] == "555566667777"


def test_held_while_an_overtime_request_waits(client, db_engine, confirmed, finished_parent):
    started(db_engine, confirmed["id"], 60)
    asked = client.post(
        f"/parent/bookings/{confirmed['id']}/overtime", json={"hours": 1}, headers=auth_for(finished_parent)
    )
    assert asked.status_code == 201
    check_out(client, db_engine, confirmed["id"], finished_parent)
    found = her_earnings(client, db_engine, confirmed).json()
    assert found["held_paise"] == 2 * HOUR and found["due_paise"] == 0
    assert found["earnings"][0]["status"] == "held" and found["earnings"][0]["due_by"] is None


def test_nothing_yet_and_only_her_own(client, db_engine, confirmed, finished_parent, free_sitter):
    from tests.test_sitter_bookings import signed_in

    checked_out(client, db_engine, confirmed, finished_parent)
    other = signed_in(db_engine, free_sitter("unwind")["id"])
    empty = client.get("/sitter/earnings", headers=auth_for(other)).json()
    assert empty == {"held_paise": 0, "due_paise": 0, "paid_paise": 0, "earnings": [], "payouts": []}
    assert client.get("/sitter/earnings", headers=auth_for(finished_parent)).status_code == 403
