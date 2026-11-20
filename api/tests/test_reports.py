# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Reports during a booking (CLAUDE.md 6.5 and 9 "New cancellation rows"; phase 7).

- Parent not home: the sitter reports it once the booking has started (only if no child is alone). She may
  leave if no parent responds within 20 minutes; the parent responds with "I have arrived", or an admin marks
  it answered (Reuben, 2026-11-19). Confirmed: the whole booking is charged; she's due ₹100 per booked hour.
- Sitter no-show: the parent reports it from 30 minutes after the start (Reuben, 2026-11-19). Confirmed: the
  parent is refunded, she gets a strike and earns nothing.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from tests.test_admin_payments import confirm, paid, verify_children  # noqa: F401
from tests.test_auto_cancel import move, status
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_cancellations import confirmed  # noqa: F401  (fixture)
from tests.test_documents import admin, as_user, client, parent, row, rows, scalar, storage  # noqa: F401
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_payments import booking, get, pay  # noqa: F401  (fixture)
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import auth_for, user  # noqa: F401  (fixture)
from tests.test_sitter_bookings import signed_in
from tests.test_verification import reviewer  # noqa: F401  (fixture)


@pytest.fixture
def admins_told(client):
    """ADMIN_ALERT_EMAILS set for the test app."""
    from app.settings import get_settings

    current = client.app.dependency_overrides[get_settings]()
    client.app.dependency_overrides[get_settings] = lambda: current.model_copy(
        update={"admin_alert_emails": ["ops@example.com"]}
    )


@pytest.fixture
def under_way(db_engine, confirmed):
    """The confirmed booking, started 5 minutes ago (2 hours long)."""
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(minutes=5))
    return confirmed


def not_home(client, sitter, booking_id, no_child_alone=True):
    return client.post(
        f"/sitter/bookings/{booking_id}/parent-not-home",
        json={"no_child_alone": no_child_alone},
        headers=auth_for(sitter),
    )


def report_id(db_engine, booking_id):
    return str(scalar(db_engine, "SELECT id FROM booking_reports WHERE booking_id = :b", b=booking_id))


def reported_minutes_ago(db_engine, booking_id, minutes):
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE booking_reports SET reported_at = :t WHERE booking_id = :b"),
            {"t": datetime.now(UTC) - timedelta(minutes=minutes), "b": booking_id},
        )


def decide(client, admin_id, rid, how, note=None):
    return client.post(f"/admin/reports/{rid}/{how}", json={"note": note}, headers=as_user(admin_id))


def to(mailbox, address):
    return [email for email in mailbox.sent if email.to == address]


# ---------- parent not home ----------


def test_only_once_the_booking_has_started_and_no_child_is_alone(client, db_engine, confirmed):
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    early = not_home(client, sitter, confirmed["id"])
    assert early.status_code == 409 and early.json()["error"]["code"] == "not_booking_time"
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(minutes=5))
    alone = not_home(client, sitter, confirmed["id"], no_child_alone=False)
    assert alone.status_code == 422 and alone.json()["error"]["code"] == "child_alone"
    assert "112" in alone.json()["error"]["message"]


def test_the_report_starts_a_20_minute_wait_and_tells_everyone(
    client, admins_told, db_engine, mailbox, under_way, finished_parent
):
    sitter = signed_in(db_engine, under_way["sitter_id"])
    response = not_home(client, sitter, under_way["id"])
    assert response.status_code == 201, response.text
    report = response.json()["report"]
    assert report["kind"] == "parent_absent" and report["status"] == "open"
    reported = datetime.fromisoformat(report["reported_at"])
    assert datetime.fromisoformat(report["can_leave_at"]) == reported + timedelta(minutes=20)
    assert "can't find you" in to(mailbox, finished_parent["email"])[-1].heading
    assert to(mailbox, "ops@example.com")[-1].heading == "A sitter says no one is home."
    assert get(client, finished_parent, under_way["id"]).json()["report"]["kind"] == "parent_absent"
    again = not_home(client, sitter, under_way["id"])
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_reported"


def test_i_have_arrived_stops_the_countdown(client, reviewer, db_engine, under_way, finished_parent):
    sitter = signed_in(db_engine, under_way["sitter_id"])
    assert not_home(client, sitter, under_way["id"]).status_code == 201
    response = client.post(f"/parent/bookings/{under_way['id']}/arrived", headers=auth_for(finished_parent))
    assert response.status_code == 200, response.text
    assert response.json()["report"]["responded_at"] is not None
    detail = client.get(f"/sitter/bookings/{under_way['id']}", headers=auth_for(sitter)).json()
    assert detail["report"]["can_leave_at"] is None  # she waits for them
    reported_minutes_ago(db_engine, under_way["id"], 25)
    late = decide(client, reviewer, report_id(db_engine, under_way["id"]), "confirm")
    assert late.status_code == 409 and late.json()["error"]["code"] == "parent_responded"


def test_an_admin_can_mark_it_answered(client, reviewer, db_engine, under_way):
    sitter = signed_in(db_engine, under_way["sitter_id"])
    assert not_home(client, sitter, under_way["id"]).status_code == 201
    response = client.post(
        f"/admin/reports/{report_id(db_engine, under_way['id'])}/answered", headers=as_user(reviewer)
    )
    assert response.status_code == 200 and response.json()["responded_at"] is not None


def test_confirmed_after_20_minutes_the_booking_is_charged_and_she_is_due_the_fee(
    client, reviewer, db_engine, mailbox, under_way, finished_parent
):
    sitter = signed_in(db_engine, under_way["sitter_id"])
    assert not_home(client, sitter, under_way["id"]).status_code == 201
    rid = report_id(db_engine, under_way["id"])
    waiting = decide(client, reviewer, rid, "confirm")
    assert waiting.status_code == 409 and waiting.json()["error"]["code"] == "still_waiting"

    (listed,) = [item for item in client.get("/admin/reports", headers=as_user(reviewer)).json() if item["id"] == rid]
    assert listed["show_up_fee_paise"] == 2 * 10_000  # ₹100 per booked hour, 2 hours
    assert listed["parent_phone"] and listed["sitter_phone"]

    reported_minutes_ago(db_engine, under_way["id"], 21)
    response = decide(client, reviewer, rid, "confirm")
    assert response.status_code == 200, response.text
    assert status(db_engine, under_way["id"]) == "parent_absent"
    assert (
        scalar(db_engine, "SELECT count(*) FROM payments WHERE booking_id = :b AND kind = 'refund'", b=under_way["id"])
        == 0
    )  # the whole booking is charged
    assert "show-up fee of ₹200" in to(mailbox, sitter["email"])[-1].body
    assert "whole booking is charged" in to(mailbox, finished_parent["email"])[-1].body
    audit = row(
        db_engine,
        "SELECT actor_id, after FROM audit_log WHERE action = 'booking_closed' AND entity_id = :b",
        b=under_way["id"],
    )
    assert audit["actor_id"] == reviewer and audit["after"]["status"] == "parent_absent"
    assert rid not in [item["id"] for item in client.get("/admin/reports", headers=as_user(reviewer)).json()]


# ---------- sitter no-show ----------


@pytest.mark.parametrize(("minutes_in", "allowed"), [(29, False), (31, True)])
def test_a_no_show_is_reported_from_30_minutes_after_the_start(
    client, db_engine, confirmed, finished_parent, minutes_in, allowed
):
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(minutes=minutes_in))
    response = client.post(f"/parent/bookings/{confirmed['id']}/no-show", headers=auth_for(finished_parent))
    if allowed:
        assert response.status_code == 201, response.text
        assert response.json()["report"]["kind"] == "sitter_no_show"
    else:
        assert response.status_code == 409 and response.json()["error"]["code"] == "too_early"


def test_a_confirmed_no_show_refunds_the_parent_and_gives_her_a_strike(
    client, reviewer, admins_told, db_engine, mailbox, confirmed, finished_parent
):
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(minutes=40))
    assert (
        client.post(f"/parent/bookings/{confirmed['id']}/no-show", headers=auth_for(finished_parent)).status_code == 201
    )
    assert to(mailbox, sitter["email"])[-1].heading == "A family says you didn't arrive."
    assert to(mailbox, "ops@example.com")[-1].heading == "A parent says their sitter didn't come."

    response = decide(client, reviewer, report_id(db_engine, confirmed["id"]), "confirm")
    assert response.status_code == 200, response.text
    assert status(db_engine, confirmed["id"]) == "sitter_no_show"
    refund = row(
        db_engine, "SELECT amount_paise FROM payments WHERE booking_id = :b AND kind = 'refund'", b=confirmed["id"]
    )
    assert refund["amount_paise"] == -confirmed["price_paise"]
    strike = row(db_engine, "SELECT reason FROM strikes WHERE booking_id = :b", b=confirmed["id"])
    assert strike["reason"] == "no_show"
    assert scalar(db_engine, "SELECT blocked_until FROM sitters WHERE profile_id = :s", s=confirmed["sitter_id"])
    assert "refunded in full" in to(mailbox, finished_parent["email"])[-1].body


# ---------- dismissing, and who may do what ----------


def test_dismissing_needs_a_reason_and_changes_nothing(
    client, reviewer, db_engine, mailbox, under_way, finished_parent
):
    sitter = signed_in(db_engine, under_way["sitter_id"])
    assert not_home(client, sitter, under_way["id"]).status_code == 201
    rid = report_id(db_engine, under_way["id"])
    assert decide(client, reviewer, rid, "dismiss").status_code == 422
    assert decide(client, reviewer, rid, "dismiss", "The parent was in the garden").status_code == 200
    assert status(db_engine, under_way["id"]) == "confirmed"
    assert scalar(db_engine, "SELECT status FROM booking_reports WHERE id = :r", r=rid) == "dismissed"
    assert decide(client, reviewer, rid, "confirm").status_code == 409  # decided once


def test_only_the_right_people(client, db_engine, under_way, finished_parent, free_sitter):
    stranger = free_sitter("unwind")
    assert not_home(client, stranger, under_way["id"]).status_code == 404
    sitter = signed_in(db_engine, under_way["sitter_id"])
    assert (
        client.post(
            f"/sitter/bookings/{under_way['id']}/parent-not-home",
            json={"no_child_alone": True},
            headers=auth_for(finished_parent),
        ).status_code
        == 403
    )
    assert not_home(client, sitter, under_way["id"]).status_code == 201
    rid = report_id(db_engine, under_way["id"])
    assert client.get("/admin/reports", headers=auth_for(finished_parent)).status_code == 403
    assert decide(client, uuid.UUID(str(sitter["id"])), rid, "confirm").status_code in (401, 403)
    assert client.post(f"/parent/bookings/{uuid.uuid4()}/arrived", headers=auth_for(finished_parent)).status_code == 404


# ---------- only a man at home (6.5; decided 2026-11-12) ----------


def man_home(client, sitter, booking_id):
    return client.post(f"/sitter/bookings/{booking_id}/only-man-home", headers=auth_for(sitter))


def test_she_may_decline_when_only_a_man_is_home(
    client, reviewer, admins_told, db_engine, mailbox, under_way, finished_parent
):
    sitter = signed_in(db_engine, under_way["sitter_id"])
    response = man_home(client, sitter, under_way["id"])
    assert response.status_code == 201, response.text
    assert response.json()["report"]["kind"] == "only_man_home"
    assert response.json()["report"]["can_leave_at"] is None  # no wait: she may leave now
    assert to(mailbox, finished_parent["email"])[-1].heading == "Lakshmi declined the booking."
    assert "only adult at home is a man" in to(mailbox, "ops@example.com")[-1].heading

    rid = report_id(db_engine, under_way["id"])
    (listed,) = [item for item in client.get("/admin/reports", headers=as_user(reviewer)).json() if item["id"] == rid]
    assert listed["show_up_fee_paise"] == 10_000  # a flat ₹100, whatever the length
    response = decide(client, reviewer, rid, "confirm")  # no 20-minute wait for this one
    assert response.status_code == 200, response.text
    assert status(db_engine, under_way["id"]) == "declined_man_at_home"
    assert (
        scalar(db_engine, "SELECT count(*) FROM payments WHERE booking_id = :b AND kind = 'refund'", b=under_way["id"])
        == 0
    )  # the whole booking is charged
    assert scalar(db_engine, "SELECT count(*) FROM strikes WHERE booking_id = :b", b=under_way["id"]) == 0
    assert "paid ₹100" in to(mailbox, sitter["email"])[-1].body
    assert "whole booking is charged" in to(mailbox, finished_parent["email"])[-1].body


def test_only_man_home_once_the_booking_has_started(client, db_engine, confirmed):
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    early = man_home(client, sitter, confirmed["id"])
    assert early.status_code == 409 and early.json()["error"]["code"] == "not_booking_time"
