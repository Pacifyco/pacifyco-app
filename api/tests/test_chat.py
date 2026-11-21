# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Chat (CLAUDE.md 6.11 and 9 "Chat"; phase 8).

- Only between a parent and sitter who have had a confirmed booking (no messaging before booking).
- New messages while they have a booking now or to come, and for 24 hours after their last one ends (Reuben,
  2026-11-21); then read-only.
- An admin reads a chat only when handling an incident, and every read is audit logged.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

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


def parent_says(client, parent_user, sitter_id, body):
    return client.post(f"/parent/chats/{sitter_id}", json={"body": body}, headers=auth_for(parent_user))


def sitter_says(client, sitter_user, parent_id, body):
    return client.post(f"/sitter/chats/{parent_id}", json={"body": body}, headers=auth_for(sitter_user))


def set_status(db_engine, booking_id, status):
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE bookings SET status = :s WHERE id = :b"), {"s": status, "b": booking_id})


def test_no_chat_before_a_confirmed_booking(client, db_engine, booking, finished_parent):
    # The fixture's booking is accepted but not paid yet.
    response = client.get(f"/parent/chats/{booking['sitter_id']}", headers=auth_for(finished_parent))
    assert response.status_code == 404
    assert parent_says(client, finished_parent, booking["sitter_id"], "Hello").status_code == 404
    assert client.get("/parent/chats", headers=auth_for(finished_parent)).json() == []


def test_they_message_each_other_once_confirmed(client, db_engine, confirmed, finished_parent):
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    sent = parent_says(client, finished_parent, confirmed["sitter_id"], "  Hi Lakshmi! Asha naps at 2.  ")
    assert sent.status_code == 201, sent.text
    chat = sent.json()
    assert chat["other_name"] == "Lakshmi" and chat["can_send"] is True
    (first,) = chat["messages"]
    assert first["from_me"] is True and first["body"] == "Hi Lakshmi! Asha naps at 2."

    theirs = client.get(f"/sitter/chats/{finished_parent['id']}", headers=auth_for(sitter)).json()
    assert [m["from_me"] for m in theirs["messages"]] == [False]
    assert sitter_says(client, sitter, finished_parent["id"], "Thanks, noted.").status_code == 201

    # Asking again with `after` (as the app does every 10 seconds) gets only the new message.
    after = first["created_at"]
    newer = client.get(
        f"/parent/chats/{confirmed['sitter_id']}", params={"after": after}, headers=auth_for(finished_parent)
    ).json()
    assert [m["body"] for m in newer["messages"]] == ["Thanks, noted."]

    (summary,) = client.get("/parent/chats", headers=auth_for(finished_parent)).json()
    assert summary["other_id"] == confirmed["sitter_id"] and summary["last_body"] == "Thanks, noted."
    assert summary["last_from_me"] is False and summary["can_send"] is True


def test_it_closes_24_hours_after_their_last_booking(client, db_engine, confirmed, finished_parent):
    set_status(db_engine, confirmed["id"], "completed")
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(hours=25))  # ended 23 hours ago
    assert parent_says(client, finished_parent, confirmed["sitter_id"], "Thank you!").status_code == 201
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(hours=27))  # ended 25 hours ago
    closed = parent_says(client, finished_parent, confirmed["sitter_id"], "One more thing")
    assert closed.status_code == 409 and closed.json()["error"]["code"] == "chat_closed"
    still = client.get(f"/parent/chats/{confirmed['sitter_id']}", headers=auth_for(finished_parent)).json()
    assert still["can_send"] is False and [m["body"] for m in still["messages"]] == ["Thank you!"]


def test_an_upcoming_booking_keeps_it_open(client, db_engine, confirmed, finished_parent):
    move(db_engine, confirmed["id"], datetime.now(UTC) + timedelta(days=5))
    assert parent_says(client, finished_parent, confirmed["sitter_id"], "See you Friday").status_code == 201


def test_messages_are_checked(client, db_engine, confirmed, finished_parent):
    blank = parent_says(client, finished_parent, confirmed["sitter_id"], "   ")
    assert blank.status_code == 422
    assert parent_says(client, finished_parent, confirmed["sitter_id"], "x" * 2001).status_code == 422


def test_only_their_own_conversations(client, db_engine, confirmed, finished_parent, free_sitter):
    other_sitter = free_sitter("unwind")
    assert sitter_says(client, other_sitter, finished_parent["id"], "Hi").status_code == 404
    assert client.get(f"/parent/chats/{uuid.uuid4()}", headers=auth_for(finished_parent)).status_code == 404
    assert client.get("/sitter/chats", headers=auth_for(finished_parent)).status_code == 403


def test_admins_read_it_only_through_an_incident_and_its_logged(
    client, reviewer, db_engine, confirmed, finished_parent
):
    assert parent_says(client, finished_parent, confirmed["sitter_id"], "Please don't give sweets").status_code == 201
    move(db_engine, confirmed["id"], datetime.now(UTC) - timedelta(minutes=5))
    raised = client.post(
        f"/parent/bookings/{confirmed['id']}/emergency", json={"kind": "emergency"}, headers=auth_for(finished_parent)
    )
    assert raised.status_code == 201, raised.text
    incident = str(scalar(db_engine, "SELECT id FROM incidents WHERE booking_id = :b", b=confirmed["id"]))
    response = client.get(f"/admin/incidents/{incident}/chat", headers=as_user(reviewer))
    assert response.status_code == 200, response.text
    assert response.json() == [
        {"sender": "parent", "body": "Please don't give sweets", "created_at": response.json()[0]["created_at"]}
    ]
    audit = row(
        db_engine,
        "SELECT actor_id, after FROM audit_log WHERE action = 'chat_read_by_admin' AND entity_id = :i",
        i=incident,
    )
    assert audit["actor_id"] == reviewer and audit["after"]["messages"] == 1
    assert client.get(f"/admin/incidents/{incident}/chat", headers=auth_for(finished_parent)).status_code == 403
