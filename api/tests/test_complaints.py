# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Complaints and grievances (CLAUDE.md 6.12; phase 10, Reuben 2026-11-23).

A parent or sitter raises a complaint (late ones flagged); admins reply within 24 hours and resolve within 48
(15 days for a serious safety matter); unresolved at its target, or if the person disagrees, it goes to the
Grievance Officer, whose written decision closes it. Appeals against a suspension or removal: within 15 days,
reviewed within 7 working days, never by the admin who made the decision.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import complaints
from app.services.availability import INDIA
from app.settings import get_settings
from tests.test_account_status import act, profile_status
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_documents import admin, as_user, client, parent, request_upload, scalar, storage  # noqa: F401
from tests.test_incidents import ADMINS, admins_told, to  # noqa: F401  (fixture)
from tests.test_jobs import SECRET, bearer
from tests.test_jobs import client as jobs_client
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_payments import booking  # noqa: F401  (fixture)
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, user  # noqa: F401  (fixture)
from tests.test_verification import reviewer  # noqa: F401  (fixture)

OFFICER = "officer@example.com"


@pytest.fixture
def other_admin(make_profile, db_engine):
    """A second admin, with clean-up of the audit rows they write."""
    admin_id = make_profile("admin", "active")
    yield admin_id
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM audit_log WHERE actor_id = :id"), {"id": admin_id})


def settings_with(client, **update):
    current = client.app.dependency_overrides[get_settings]()
    client.app.dependency_overrides[get_settings] = lambda: current.model_copy(update=update)


def raise_one(client, who, **body):
    body = {"type": "payment", "description": "I was charged twice.", **body}
    return client.post("/me/complaints", json=body, headers=auth_for(who))


def admin_post(client, admin_id, complaint_id, path, **body):
    return client.post(f"/admin/complaints/{complaint_id}/{path}", json=body or None, headers=as_user(admin_id))


def admin_view(client, admin_id, complaint_id):
    response = client.get(f"/admin/complaints/{complaint_id}", headers=as_user(admin_id))
    assert response.status_code == 200, response.text
    return response.json()


def queue(client, admin_id, view="open"):
    return [item["id"] for item in client.get(f"/admin/complaints?view={view}", headers=as_user(admin_id)).json()]


def at(value: str) -> datetime:
    return datetime.fromisoformat(value)


# ---------- raising one ----------


def test_a_complaint_has_targets_and_tells_the_admins(client, mailbox, admins_told, reviewer, finished_parent):
    mailbox.sent.clear()
    response = raise_one(client, finished_parent, description="  I was charged twice.  ")
    assert response.status_code == 201, response.text
    made = response.json()
    assert made["status"] == "open" and made["description"] == "I was charged twice." and made["late"] is False
    assert at(made["reply_by"]) - at(made["created_at"]) == timedelta(hours=24)
    assert at(made["resolve_by"]) - at(made["created_at"]) == timedelta(hours=48)
    assert made["can_escalate"] is False and made["can_attach"] is True and made["messages"] == []

    (alert,) = to(mailbox, ADMINS[0])
    assert alert.button_url.endswith(f"/admin/complaints/{made['id']}")
    assert "Meera" not in alert.body and "charged" not in alert.body  # no names or details by email
    assert [item["id"] for item in client.get("/me/complaints", headers=auth_for(finished_parent)).json()] == [
        made["id"]
    ]
    assert made["id"] in queue(client, reviewer)


def test_late_when_it_happened_over_a_day_ago(client, finished_parent):
    today = datetime.now(UTC).astimezone(INDIA).date()
    yesterday = raise_one(client, finished_parent, happened_on=(today - timedelta(days=1)).isoformat())
    assert yesterday.json()["late"] is False
    older = raise_one(client, finished_parent, happened_on=(today - timedelta(days=2)).isoformat())
    assert older.json()["late"] is True
    future = raise_one(client, finished_parent, happened_on=(today + timedelta(days=1)).isoformat())
    assert future.status_code == 422 and future.json()["error"]["code"] == "date_in_future"


def test_about_their_own_booking_only(client, booking, finished_parent, free_sitter):
    mine = raise_one(client, finished_parent, type="booking", booking_id=booking["id"])
    assert mine.status_code == 201 and mine.json()["booking_id"] == booking["id"]
    stranger = free_sitter("unwind")
    other = raise_one(client, stranger, type="booking", booking_id=booking["id"])
    assert other.status_code == 404
    no_booking = raise_one(client, finished_parent, type="booking")
    assert no_booking.status_code == 422 and no_booking.json()["error"]["code"] == "booking_needed"
    appeal = raise_one(client, finished_parent, type="suspension")
    assert appeal.status_code == 422 and appeal.json()["error"]["code"] == "invalid_type"
    empty = raise_one(client, finished_parent, description="   ")
    assert empty.status_code == 422


def test_only_their_own_complaints(client, finished_parent, free_sitter, admin):
    made = raise_one(client, finished_parent).json()
    stranger = free_sitter("unwind")
    assert client.get(f"/me/complaints/{made['id']}", headers=auth_for(stranger)).status_code == 404
    write = client.post(f"/me/complaints/{made['id']}/messages", json={"body": "Hi"}, headers=auth_for(stranger))
    assert write.status_code == 404
    assert client.get("/me/complaints", headers=auth_for(stranger)).json() == []
    assert client.get("/me/complaints", headers=as_user(admin)).status_code == 403  # admins use their own pages


# ---------- replies and resolving ----------


def test_replies_in_writing(client, mailbox, admins_told, reviewer, finished_parent):
    made = raise_one(client, finished_parent).json()
    mailbox.sent.clear()
    reply = admin_post(client, reviewer, made["id"], "messages", body="Sorry. We're looking into it.")
    assert reply.status_code == 200, reply.text
    assert reply.json()["status"] == "replied" and reply.json()["first_reply_at"] is not None
    (told,) = to(mailbox, finished_parent["email"])
    assert "We're looking into it." in told.body and told.button_url.endswith(f"/parent/help/{made['id']}")

    answer = client.post(
        f"/me/complaints/{made['id']}/messages", json={"body": "Thank you."}, headers=auth_for(finished_parent)
    )
    assert [(item["from_pacifyco"], item["body"]) for item in answer.json()["messages"]] == [
        (True, "Sorry. We're looking into it."),
        (False, "Thank you."),
    ]
    assert to(mailbox, ADMINS[0])[-1].subject == "A new message on a complaint"
    assert admin_view(client, reviewer, made["id"])["messages"][1]["from_pacifyco"] is False


def test_a_serious_safety_matter_has_15_days(client, reviewer, finished_parent):
    made = raise_one(client, finished_parent, type="other", description="The sitter left the gate open.").json()
    marked = admin_post(client, reviewer, made["id"], "serious", serious=True).json()
    assert marked["serious"] is True
    assert at(marked["resolve_by"]) - at(marked["created_at"]) == timedelta(days=15)
    unmarked = admin_post(client, reviewer, made["id"], "serious", serious=False).json()
    assert at(unmarked["resolve_by"]) - at(unmarked["created_at"]) == timedelta(hours=48)


def test_resolved_then_the_person_disagrees(client, mailbox, admins_told, reviewer, finished_parent):
    made = raise_one(client, finished_parent).json()
    early = client.post(
        f"/me/complaints/{made['id']}/escalate", json={"body": "Too slow"}, headers=auth_for(finished_parent)
    )
    assert early.status_code == 409 and early.json()["error"]["code"] == "cannot_escalate"

    mailbox.sent.clear()
    done = admin_post(client, reviewer, made["id"], "resolve", body="We refunded the second charge.")
    assert done.json()["status"] == "resolved" and done.json()["resolution"] == "We refunded the second charge."
    assert "We refunded the second charge." in to(mailbox, finished_parent["email"])[-1].body
    assert made["id"] in queue(client, reviewer, "done")

    mine = client.get(f"/me/complaints/{made['id']}", headers=auth_for(finished_parent)).json()
    assert mine["can_escalate"] is True
    mailbox.sent.clear()
    up = client.post(
        f"/me/complaints/{made['id']}/escalate",
        json={"body": "It still shows twice."},
        headers=auth_for(finished_parent),
    )
    assert up.status_code == 200 and up.json()["status"] == "escalated"
    assert "Grievance Officer" in to(mailbox, finished_parent["email"])[-1].body
    assert to(mailbox, ADMINS[0])[-1].button_url.endswith("/admin/complaints?view=escalated")  # no officer set
    seen = admin_view(client, reviewer, made["id"])
    assert seen["escalated_by_person"] is True and seen["escalation_note"] == "It still shows twice."
    assert at(seen["acknowledge_by"]) - at(seen["escalated_at"]) == timedelta(hours=24)
    assert at(seen["decide_by"]) - at(seen["escalated_at"]) == timedelta(days=15)


# ---------- the Grievance Officer ----------


def escalated(client, reviewer, who):
    made = raise_one(client, who).json()
    admin_post(client, reviewer, made["id"], "resolve", body="Done.")
    client.post(f"/me/complaints/{made['id']}/escalate", json={"body": "No."}, headers=auth_for(who))
    return made["id"]


def test_only_the_officer_handles_escalated_ones(client, db_engine, mailbox, reviewer, other_admin, finished_parent):
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE profiles SET email = :e WHERE id = :id"), {"e": OFFICER, "id": other_admin})
    settings_with(client, grievance_officer_email=OFFICER.upper(), admin_alert_emails=ADMINS)
    mailbox.sent.clear()
    complaint_id = escalated(client, reviewer, finished_parent)
    escalations = [email.to for email in mailbox.sent if email.subject.endswith("escalated to the Grievance Officer")]
    assert escalations == [OFFICER.upper()]  # as configured; matched to the account whatever the case

    seen = admin_view(client, reviewer, complaint_id)
    assert seen["cannot_handle"] == "This is with the Grievance Officer." and seen["is_officer"] is False
    refused = admin_post(client, reviewer, complaint_id, "officer-decision", body="Upheld.")
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "cannot_handle"
    assert admin_post(client, reviewer, complaint_id, "messages", body="Hello").status_code == 403

    assert admin_view(client, other_admin, complaint_id)["is_officer"] is True
    acknowledged = admin_post(client, other_admin, complaint_id, "acknowledge")
    assert acknowledged.json()["officer_acknowledged_at"] is not None
    mailbox.sent.clear()
    decided = admin_post(client, other_admin, complaint_id, "officer-decision", body="Refunded in full, because…")
    assert decided.json()["status"] == "closed" and decided.json()["officer_decision"] == "Refunded in full, because…"
    assert "Refunded in full" in to(mailbox, finished_parent["email"])[-1].body

    closed = client.post(
        f"/me/complaints/{complaint_id}/messages", json={"body": "Thanks"}, headers=auth_for(finished_parent)
    )
    assert closed.status_code == 409 and closed.json()["error"]["code"] == "complaint_closed"
    assert complaint_id in queue(client, reviewer, "done")


def test_overdue_complaints_go_to_the_officer(client, db_engine, mailbox, reviewer, finished_parent):
    made = raise_one(client, finished_parent).json()
    serious = raise_one(client, finished_parent, type="other").json()
    admin_post(client, reviewer, serious["id"], "serious", serious=True)
    with db_engine.begin() as conn:  # both raised 3 days ago
        conn.execute(
            text(
                "UPDATE complaints SET created_at = created_at - interval '3 days',"
                " reply_by = reply_by - interval '3 days', resolve_by = resolve_by - interval '3 days'"
                " WHERE id IN (:a, :b)"
            ),
            {"a": made["id"], "b": serious["id"]},
        )
    assert admin_view(client, reviewer, made["id"])["overdue"] is True
    mailbox.sent.clear()
    ran = jobs_client(db_engine, mailbox=mailbox, admin_alert_emails=",".join(ADMINS)).post(
        "/internal/jobs/frequent", headers=bearer(SECRET)
    )
    assert ran.status_code == 200, ran.text
    after = admin_view(client, reviewer, made["id"])
    assert after["status"] == "escalated" and after["escalated_by_person"] is False
    assert admin_view(client, reviewer, serious["id"])["status"] == "open"  # 15 days: not yet
    assert "in time" in to(mailbox, finished_parent["email"])[-1].body
    assert made["id"] in queue(client, reviewer, "escalated")


# ---------- appeals ----------


def appeal(client, who, body="I didn't do this."):
    return client.post("/me/appeal", json={"body": body}, headers=auth_for(who))


def test_an_appeal_against_a_suspension(
    client, db_engine, mailbox, admins_told, reviewer, other_admin, finished_parent
):
    assert client.get("/me/appeal", headers=auth_for(finished_parent)).json()["decision"] is None
    assert appeal(client, finished_parent).json()["error"]["code"] == "nothing_to_appeal"
    assert act(client, reviewer, finished_parent["id"], "suspend", reason="Rude to a sitter.").status_code == 200

    state = client.get("/me/appeal", headers=auth_for(finished_parent)).json()
    assert state["decision"]["action"] == "suspended" and state["decision"]["reason"] == "Rude to a sitter."
    assert state["can_appeal"] is True and state["appeal"] is None
    blocked = raise_one(client, finished_parent)
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "account_blocked"

    mailbox.sent.clear()
    sent = appeal(client, finished_parent)
    assert sent.status_code == 201, sent.text
    made = sent.json()["appeal"]
    assert made["type"] == "suspension" and sent.json()["can_appeal"] is False
    assert to(mailbox, ADMINS[0])[-1].subject == "A new appeal on Pacifyco"
    assert appeal(client, finished_parent).json()["error"]["code"] == "already_appealed"
    assert made["id"] in queue(client, reviewer, "appeals") and made["id"] not in queue(client, reviewer)
    assert at(made["resolve_by"]) == complaints.working_days_after(_db(db_engine), at(made["created_at"]), 7)

    # The admin who suspended them can't touch it; another admin can.
    seen = admin_view(client, reviewer, made["id"])
    assert seen["decision"]["by_id"] == str(reviewer) and "another admin" in seen["cannot_handle"]
    for path, body in (("messages", {"body": "Hi"}), ("appeal", {"outcome": "rejected", "note": "No."})):
        refused = admin_post(client, reviewer, made["id"], path, **body)
        assert refused.status_code == 403 and refused.json()["error"]["code"] == "cannot_handle"
    assert admin_view(client, other_admin, made["id"])["cannot_handle"] is None

    # They can write on it while suspended, and read only it.
    write = client.post(
        f"/me/complaints/{made['id']}/messages", json={"body": "More"}, headers=auth_for(finished_parent)
    )
    assert write.status_code == 200
    assert [item["type"] for item in client.get("/me/complaints", headers=auth_for(finished_parent)).json()] == [
        "suspension"
    ]

    wrong = admin_post(client, other_admin, made["id"], "appeal", outcome="rejected", note="x", reinstate=True)
    assert wrong.status_code == 422
    mailbox.sent.clear()
    upheld = admin_post(
        client, other_admin, made["id"], "appeal", outcome="upheld", note="A misunderstanding.", reinstate=True
    )
    assert upheld.status_code == 200, upheld.text
    assert upheld.json()["appeal_outcome"] == "upheld" and upheld.json()["status"] == "resolved"
    assert profile_status(db_engine, finished_parent["id"]) in ("active", "pending")
    assert "active again" in to(mailbox, finished_parent["email"])[-1].body


def _db(db_engine):
    return Session(bind=db_engine)


def test_upheld_without_reinstating_and_rejected(client, db_engine, reviewer, other_admin, finished_parent):
    act(client, reviewer, finished_parent["id"], "suspend")
    made = appeal(client, finished_parent).json()["appeal"]
    upheld = admin_post(client, other_admin, made["id"], "appeal", outcome="upheld", note="Fair point.")
    assert upheld.json()["appeal_outcome"] == "upheld"
    assert profile_status(db_engine, finished_parent["id"]) == "suspended"  # reinstated by hand later
    again = admin_post(client, other_admin, made["id"], "appeal", outcome="rejected", note="No.")
    assert again.status_code == 409


def test_appeals_within_15_days(client, db_engine, reviewer, finished_parent):
    act(client, reviewer, finished_parent["id"], "remove")
    with db_engine.begin() as conn:  # as the owner: account_actions is append-only for the API
        conn.execute(
            text("UPDATE account_actions SET created_at = now() - interval '16 days' WHERE profile_id = :p"),
            {"p": finished_parent["id"]},
        )
    state = client.get("/me/appeal", headers=auth_for(finished_parent)).json()
    assert state["decision"]["action"] == "removed" and state["can_appeal"] is False
    assert appeal(client, finished_parent).json()["error"]["code"] == "appeal_too_late"


def test_any_admin_handles_an_appeal_against_the_rules(client, db_engine, reviewer, finished_parent):
    with db_engine.begin() as conn:  # suspended by the rules (a theft or abuse report), no admin
        conn.execute(text("UPDATE profiles SET status = 'suspended' WHERE id = :p"), {"p": finished_parent["id"]})
        conn.execute(
            text(
                "INSERT INTO account_actions (profile_id, action, kind, reason)"
                " VALUES (:p, 'suspended', 'safety', 'A report about a booking.')"
            ),
            {"p": finished_parent["id"]},
        )
    made = appeal(client, finished_parent).json()["appeal"]
    assert admin_view(client, reviewer, made["id"])["cannot_handle"] is None


# ---------- working days and holidays ----------


def test_seven_working_days_skip_weekends_and_holidays(client, db_engine, reviewer):
    monday = date(2031, 3, 3)
    start = datetime(2031, 3, 3, 10, tzinfo=INDIA)  # Monday 10 am
    with _db(db_engine) as db:
        # Tue Wed Thu Fri, Mon Tue Wed: the 7th working day is Wednesday 12 March; due by its end.
        assert complaints.working_days_after(db, start, 7) == datetime(2031, 3, 13, tzinfo=INDIA)
    added = client.post("/admin/holidays", json={"day": "2031-03-05", "name": "Test day"}, headers=as_user(reviewer))
    try:
        assert added.status_code == 201 and {"day": "2031-03-05", "name": "Test day"} in added.json()
        duplicate = client.post(
            "/admin/holidays", json={"day": "2031-03-05", "name": "Again"}, headers=as_user(reviewer)
        )
        assert duplicate.status_code == 409
        with _db(db_engine) as db:
            assert complaints.working_days_after(db, start, 7) == datetime(2031, 3, 14, tzinfo=INDIA)
        assert monday.weekday() == 0
    finally:
        removed = client.delete("/admin/holidays/2031-03-05", headers=as_user(reviewer))
    assert removed.status_code == 200 and {"day": "2031-03-05", "name": "Test day"} not in removed.json()
    assert client.delete("/admin/holidays/2031-03-05", headers=as_user(reviewer)).status_code == 404


# ---------- attachments ----------


def test_up_to_three_files_on_their_own_complaint(client, storage, reviewer, finished_parent, free_sitter):
    made = raise_one(client, finished_parent).json()
    body = {"type": "complaint_attachment", "complaint_id": made["id"]}
    for _ in range(3):
        assert client.post("/documents/upload-url", json=body, headers=auth_for(finished_parent)).status_code == 201
    fourth = client.post("/documents/upload-url", json=body, headers=auth_for(finished_parent))
    assert fourth.status_code == 409 and fourth.json()["error"]["code"] == "too_many_attachments"
    stranger = free_sitter("unwind")
    assert client.post("/documents/upload-url", json=body, headers=auth_for(stranger)).status_code == 404
    bare = client.post(
        "/documents/upload-url", json={"type": "complaint_attachment"}, headers=auth_for(finished_parent)
    )
    assert bare.status_code == 422
    other = request_upload(client, finished_parent, "government_id")
    assert other.status_code == 201  # other documents don't need a complaint

    second = raise_one(client, finished_parent).json()
    ticket = client.post(
        "/documents/upload-url",
        json={"type": "complaint_attachment", "complaint_id": second["id"]},
        headers=auth_for(finished_parent),
    ).json()
    storage.put(f"{finished_parent['id']}/{ticket['document_id']}", b"%PDF-1.4 test")
    confirmed = client.post(f"/documents/{ticket['document_id']}/confirm", headers=auth_for(finished_parent))
    assert confirmed.status_code == 200
    (attached,) = admin_view(client, reviewer, second["id"])["attachments"]
    assert attached["id"] == ticket["document_id"] and attached["type"] == "complaint_attachment"
    mine = client.get(f"/me/complaints/{second['id']}", headers=auth_for(finished_parent)).json()
    assert [item["id"] for item in mine["attachments"]] == [ticket["document_id"]]


def test_unknown_view_refused(client, reviewer):
    response = client.get("/admin/complaints?view=everything", headers=as_user(reviewer))
    assert response.status_code == 422
    assert uuid.UUID(str(reviewer))


# ---------- the audit trail (CLAUDE.md 9 "Audit") and the officer's own decisions ----------


def audit_actions(db_engine, entity_id):
    with db_engine.connect() as conn:
        return [
            (row.action, row.actor_id)
            for row in conn.execute(
                text("SELECT action, actor_id FROM audit_log WHERE entity_id = :e ORDER BY id"), {"e": str(entity_id)}
            )
        ]


def test_every_step_of_a_complaint_is_audit_logged(client, db_engine, reviewer, finished_parent):
    made = raise_one(client, finished_parent).json()
    admin_post(client, reviewer, made["id"], "messages", body="Looking into it.")
    admin_post(client, reviewer, made["id"], "messages", body="Still looking.")  # only the first reply is logged
    admin_post(client, reviewer, made["id"], "serious", serious=True)
    admin_post(client, reviewer, made["id"], "serious", serious=False)
    admin_post(client, reviewer, made["id"], "resolve", body="Done.")
    client.post(f"/me/complaints/{made['id']}/escalate", json={"body": "No."}, headers=auth_for(finished_parent))
    admin_post(client, reviewer, made["id"], "acknowledge")
    admin_post(client, reviewer, made["id"], "officer-decision", body="Upheld, because…")
    person, admin = uuid.UUID(str(finished_parent["id"])), reviewer
    assert audit_actions(db_engine, made["id"]) == [
        ("complaint_raised", person),
        ("complaint_replied", admin),
        ("complaint_marked_serious", admin),
        ("complaint_unmarked_serious", admin),
        ("complaint_resolved", admin),
        ("complaint_escalated", person),
        ("complaint_acknowledged_by_officer", admin),
        ("complaint_decided_by_officer", admin),
    ]


def test_an_appeal_and_holidays_are_audit_logged(client, db_engine, reviewer, other_admin, finished_parent):
    act(client, reviewer, finished_parent["id"], "suspend")
    made = appeal(client, finished_parent).json()["appeal"]
    admin_post(client, other_admin, made["id"], "appeal", outcome="rejected", note="It stands.")
    person = uuid.UUID(str(finished_parent["id"]))
    assert audit_actions(db_engine, made["id"]) == [("appeal_raised", person), ("appeal_decided", other_admin)]

    try:
        client.post("/admin/holidays", json={"day": "2031-10-02", "name": "Gandhi Jayanti"}, headers=as_user(reviewer))
        client.delete("/admin/holidays/2031-10-02", headers=as_user(reviewer))
        assert audit_actions(db_engine, "2031-10-02") == [("holiday_added", reviewer), ("holiday_removed", reviewer)]
    finally:
        with db_engine.begin() as conn:
            conn.execute(text("DELETE FROM public_holidays WHERE day = '2031-10-02'"))


def test_the_officer_cant_handle_an_escalated_appeal_against_their_own_decision(
    client, db_engine, reviewer, other_admin, finished_parent
):
    """Every admin is the officer while GRIEVANCE_OFFICER_EMAIL is empty, but not on their own decision (6.12)."""
    act(client, reviewer, finished_parent["id"], "suspend")
    made = appeal(client, finished_parent).json()["appeal"]
    admin_post(client, other_admin, made["id"], "appeal", outcome="rejected", note="It stands.")
    sent = client.post(
        f"/me/complaints/{made['id']}/escalate", json={"body": "Unfair."}, headers=auth_for(finished_parent)
    )
    assert sent.json()["status"] == "escalated"
    refused = admin_post(client, reviewer, made["id"], "acknowledge")
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "cannot_handle"
    assert admin_post(client, other_admin, made["id"], "acknowledge").status_code == 200
