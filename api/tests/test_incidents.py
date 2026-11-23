# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""The Emergency and Issues buttons (CLAUDE.md 6.9 and 9 "Incidents"; phase 8).

- On a booking from its start until 1 hour after its end or check-out (Reuben, 2026-11-21).
- Emergency: every admin address is emailed at once; it stays at the top of the admin panel until
  acknowledged. A parent's theft or abuse report suspends the sitter until an admin resolves it. An open
  incident holds her payout for that booking.
- Issues: a complaint linked to the booking, emailed to admins, marked replied and resolved.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.services import incidents
from tests.test_admin_payments import confirm, paid, verify_children  # noqa: F401
from tests.test_auto_cancel import move
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_cancellations import confirmed  # noqa: F401  (fixture)
from tests.test_documents import admin, as_user, client, parent, row, rows, scalar, storage  # noqa: F401
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_payments import booking, get, pay  # noqa: F401  (fixture)
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import auth_for, user  # noqa: F401  (fixture)
from tests.test_sitter_bookings import signed_in
from tests.test_verification import reviewer  # noqa: F401  (fixture)

ADMINS = ["ops@example.com", "founders@example.com"]


@pytest.fixture
def admins_told(client):
    from app.settings import get_settings

    current = client.app.dependency_overrides[get_settings]()
    client.app.dependency_overrides[get_settings] = lambda: current.model_copy(update={"admin_alert_emails": ADMINS})


@pytest.fixture
def under_way(db_engine, confirmed):
    """The confirmed booking, started 5 minutes ago (2 hours long)."""
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(minutes=5))
    return confirmed


def emergency(client, who, booking_id, kind, role="parent", note=None):
    return client.post(
        f"/{role}/bookings/{booking_id}/emergency", json={"kind": kind, "note": note}, headers=auth_for(who)
    )


def issue(client, who, booking_id, topic, role="parent", note=None):
    return client.post(
        f"/{role}/bookings/{booking_id}/issues", json={"topic": topic, "note": note}, headers=auth_for(who)
    )


def incident_id(db_engine, booking_id):
    return str(scalar(db_engine, "SELECT id FROM incidents WHERE booking_id = :b", b=booking_id))


def to(mailbox, address):
    return [email for email in mailbox.sent if email.to == address]


# ---------- when ----------


def test_only_from_the_start_until_an_hour_after_the_end(client, db_engine, confirmed, finished_parent):
    early = emergency(client, finished_parent, confirmed["id"], "emergency")
    assert early.status_code == 409 and early.json()["error"]["code"] == "not_during_booking"
    assert get(client, finished_parent, confirmed["id"]).json()["buttons_open"] is False
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(hours=2, minutes=50))  # ended 50 minutes ago
    assert get(client, finished_parent, confirmed["id"]).json()["buttons_open"] is True
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(hours=3, minutes=10))  # ended 70 minutes ago
    late = issue(client, finished_parent, confirmed["id"], "running_late")
    assert late.status_code == 409 and late.json()["error"]["code"] == "not_during_booking"


# ---------- emergency ----------


def test_an_emergency_emails_every_admin_at_once(client, admins_told, db_engine, mailbox, under_way, finished_parent):
    response = emergency(client, finished_parent, under_way["id"], "emergency", note="Child fell, ambulance called")
    assert response.status_code == 201, response.text
    assert response.json()["incident"]["kind"] == "emergency" and response.json()["incident"]["status"] == "open"
    for address in ADMINS:
        (alert,) = to(mailbox, address)
        assert alert.subject.startswith("EMERGENCY") and alert.button_url.endswith("/admin/incidents")
    saved = row(
        db_engine, "SELECT note, status, suspended_sitter FROM incidents WHERE booking_id = :b", b=under_way["id"]
    )
    assert saved["note"] == "Child fell, ambulance called" and saved["status"] == "open"
    assert saved["suspended_sitter"] is False


def test_an_open_incident_holds_her_payout(db_engine, client, reviewer, under_way, finished_parent):
    assert emergency(client, finished_parent, under_way["id"], "emergency").status_code == 201
    with Session(db_engine) as db:
        assert incidents.has_open_incident(db, uuid.UUID(under_way["id"])) is True
    rid = incident_id(db_engine, under_way["id"])
    assert (
        client.post(f"/admin/incidents/{rid}/resolve", json={"note": "All fine"}, headers=as_user(reviewer)).status_code
        == 200
    )
    with Session(db_engine) as db:
        assert incidents.has_open_incident(db, uuid.UUID(under_way["id"])) is False


@pytest.mark.parametrize("kind", ["theft", "abuse"])
def test_a_parents_theft_or_abuse_report_suspends_the_sitter(
    client, reviewer, db_engine, mailbox, under_way, finished_parent, kind
):
    sitter = signed_in(db_engine, under_way["sitter_id"])
    assert emergency(client, finished_parent, under_way["id"], kind).status_code == 201
    assert scalar(db_engine, "SELECT status FROM profiles WHERE id = :s", s=under_way["sitter_id"]) == "suspended"
    blocked = client.get("/sitter/bookings", headers=auth_for(sitter))
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "account_blocked"
    assert to(mailbox, sitter["email"])[-1].heading == "Your account is suspended for now."

    rid = incident_id(db_engine, under_way["id"])
    resolved = client.post(
        f"/admin/incidents/{rid}/resolve",
        json={"note": "Misunderstanding", "reinstate_sitter": True},
        headers=as_user(reviewer),
    )
    assert resolved.status_code == 200
    assert scalar(db_engine, "SELECT status FROM profiles WHERE id = :s", s=under_way["sitter_id"]) == "active"
    assert to(mailbox, sitter["email"])[-1].heading == "Your account is active again."


def test_resolved_without_reinstating_she_stays_suspended(client, reviewer, db_engine, under_way, finished_parent):
    assert emergency(client, finished_parent, under_way["id"], "theft").status_code == 201
    rid = incident_id(db_engine, under_way["id"])
    response = client.post(f"/admin/incidents/{rid}/resolve", json={"note": "Confirmed"}, headers=as_user(reviewer))
    assert response.status_code == 200
    assert scalar(db_engine, "SELECT status FROM profiles WHERE id = :s", s=under_way["sitter_id"]) == "suspended"
    audit = row(db_engine, "SELECT after FROM audit_log WHERE action = 'incident_resolved' AND entity_id = :i", i=rid)
    assert audit["after"]["sitter_reinstated"] is False


def test_the_sitters_choices_suspend_no_one(client, db_engine, under_way):
    sitter = signed_in(db_engine, under_way["sitter_id"])
    wrong = emergency(client, sitter, under_way["id"], "theft", role="sitter")
    assert wrong.status_code == 422 and wrong.json()["error"]["code"] == "invalid_kind"
    response = emergency(client, sitter, under_way["id"], "sitter_unsafe", role="sitter", note="Shouting")
    assert response.status_code == 201, response.text
    assert response.json()["incident"]["kind"] == "sitter_unsafe"
    assert scalar(db_engine, "SELECT status FROM profiles WHERE id = :s", s=under_way["sitter_id"]) == "active"


def test_admins_acknowledge_then_resolve(client, reviewer, db_engine, under_way, finished_parent):
    assert emergency(client, finished_parent, under_way["id"], "emergency").status_code == 201
    rid = incident_id(db_engine, under_way["id"])
    (listed,) = [item for item in client.get("/admin/incidents", headers=as_user(reviewer)).json() if item["id"] == rid]
    assert listed["status"] == "open" and listed["raised_by"] == "parent"
    assert listed["parent_phone"] and listed["sitter_phone"]
    acked = client.post(f"/admin/incidents/{rid}/acknowledge", headers=as_user(reviewer))
    assert acked.status_code == 200 and acked.json()["status"] == "acknowledged"
    assert (
        client.post(f"/admin/incidents/{rid}/resolve", json={"note": "  "}, headers=as_user(reviewer)).status_code
        == 422
    )
    assert (
        client.post(f"/admin/incidents/{rid}/resolve", json={"note": "Sorted"}, headers=as_user(reviewer)).status_code
        == 200
    )
    assert rid not in [item["id"] for item in client.get("/admin/incidents", headers=as_user(reviewer)).json()]
    again = client.post(f"/admin/incidents/{rid}/resolve", json={"note": "x"}, headers=as_user(reviewer))
    assert again.status_code == 409


# ---------- issues ----------


def test_an_issue_is_a_complaint_for_admins(
    client, reviewer, admins_told, db_engine, mailbox, under_way, finished_parent
):
    response = issue(client, finished_parent, under_way["id"], "running_late")
    assert response.status_code == 201, response.text
    saved = row(
        db_engine, "SELECT type, topic, description, status FROM complaints WHERE booking_id = :b", b=under_way["id"]
    )
    assert dict(saved) == {"type": "booking", "topic": "running_late", "description": "Running late", "status": "open"}
    cid = response.json()["id"]
    assert to(mailbox, ADMINS[0])[-1].button_url.endswith(f"/admin/complaints/{cid}")

    # It's a complaint like any other (6.12): with targets, in the admins' queue, answered in writing.
    queue = client.get("/admin/complaints", headers=as_user(reviewer)).json()
    (listed,) = [item for item in queue if item["id"] == cid]
    assert listed["person_role"] == "parent" and listed["topic"] == "running_late" and not listed["late"]
    reply = client.post(
        f"/admin/complaints/{cid}/messages", json={"body": "On our way to help."}, headers=as_user(reviewer)
    )
    assert reply.json()["status"] == "replied"
    assert scalar(db_engine, "SELECT first_reply_at FROM complaints WHERE id = :c", c=cid) is not None
    done = client.post(f"/admin/complaints/{cid}/resolve", json={"body": "Sorted."}, headers=as_user(reviewer))
    assert done.json()["status"] == "resolved"
    assert cid not in [item["id"] for item in client.get("/admin/complaints", headers=as_user(reviewer)).json()]


def test_something_else_needs_a_note(client, db_engine, under_way):
    sitter = signed_in(db_engine, under_way["sitter_id"])
    bare = issue(client, sitter, under_way["id"], "other", role="sitter")
    assert bare.status_code == 422 and bare.json()["error"]["code"] == "note_needed"
    assert issue(client, sitter, under_way["id"], "other", role="sitter", note="No key left out").status_code == 201


def test_only_the_right_people(client, db_engine, under_way, finished_parent, free_sitter):
    stranger = free_sitter("unwind")
    assert emergency(client, stranger, under_way["id"], "emergency", role="sitter").status_code == 404
    assert client.get("/admin/incidents", headers=auth_for(finished_parent)).status_code == 403
    assert client.get("/admin/complaints", headers=auth_for(finished_parent)).status_code == 403
