# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Strikes (CLAUDE.md 6.6 and 9 "Strikes"; phase 7).

- The ladder: a strike blocks new bookings for 24 hours, then 3 days, 1 week, 2 weeks; the 5th removes
  her. Only strikes from the last 6 months count.
- A blocked sitter is hidden from parents, can't be booked and can't accept requests; her confirmed
  bookings stay.
- Admins add or remove a strike with a reason (audit logged). She can send a doctor's note for a late
  cancellation (6.5).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import StrikeReason
from app.services import strikes
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_documents import admin, as_user, client, parent, row, rows, scalar, storage  # noqa: F401
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_payments import booking  # noqa: F401  (fixture)
from tests.test_requests import answer, request  # noqa: F401
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import auth_for, user  # noqa: F401  (fixture)
from tests.test_verification import reviewer, upload  # noqa: F401  (fixture)


def give(db_engine, sitter_id, at: datetime, reason=StrikeReason.late_cancellation):
    with Session(db_engine) as db:
        done = strikes.give(db, None, uuid.UUID(str(sitter_id)), reason, at)
        db.commit()
        return done.blocked_until, done.removed


def blocked_until(db_engine, sitter_id):
    return scalar(db_engine, "SELECT blocked_until FROM sitters WHERE profile_id = :s", s=sitter_id)


def their_strikes(client, sitter):
    response = client.get("/sitter/strikes", headers=auth_for(sitter))
    assert response.status_code == 200, response.text
    return response.json()


# ---------- the ladder ----------


@pytest.mark.parametrize(
    ("count", "block"),
    [(1, timedelta(hours=24)), (2, timedelta(days=3)), (3, timedelta(weeks=1)), (4, timedelta(weeks=2))],
)
def test_the_ladder(db_engine, free_sitter, count, block):
    sitter = free_sitter("unwind")
    now = datetime.now(UTC)
    for _ in range(count - 1):
        give(db_engine, sitter["id"], now - timedelta(days=30))
    until, removed = give(db_engine, sitter["id"], now)
    assert until == now + block and removed is False


def test_the_fifth_strike_removes_her(client, db_engine, free_sitter):
    sitter = free_sitter("unwind")
    now = datetime.now(UTC)
    for days_ago in (100, 80, 60, 40):
        give(db_engine, sitter["id"], now - timedelta(days=days_ago))
    _, removed = give(db_engine, sitter["id"], now)
    assert removed is True
    assert scalar(db_engine, "SELECT status FROM profiles WHERE id = :s", s=sitter["id"]) == "removed"
    response = client.get("/sitter/bookings", headers=auth_for(sitter))
    assert response.status_code == 403 and response.json()["error"]["code"] == "account_blocked"
    audit = row(
        db_engine, "SELECT after FROM audit_log WHERE action = 'sitter_removed' AND entity_id = :s", s=str(sitter["id"])
    )
    assert audit["after"] == {"status": "removed", "reason": "fifth_strike"}


def test_only_strikes_from_the_last_6_months_count(db_engine, free_sitter):
    sitter = free_sitter("unwind")
    now = datetime.now(UTC)
    for days_ago in (300, 250, 200):  # all older than 6 months
        give(db_engine, sitter["id"], now - timedelta(days=days_ago))
    until, _ = give(db_engine, sitter["id"], now)
    assert until == now + timedelta(hours=24)  # counts as her first


def test_a_removed_strike_doesnt_count(client, reviewer, db_engine, free_sitter):
    sitter = free_sitter("unwind")
    now = datetime.now(UTC)
    give(db_engine, sitter["id"], now - timedelta(days=10))
    first = scalar(db_engine, "SELECT id FROM strikes WHERE sitter_id = :s", s=sitter["id"])
    response = client.post(
        f"/admin/strikes/{first}/remove", json={"reason": "Doctor's note"}, headers=as_user(reviewer)
    )
    assert response.status_code == 200, response.text
    until, _ = give(db_engine, sitter["id"], now)
    assert until == now + timedelta(hours=24)


# ---------- what a block does ----------


def test_a_blocked_sitter_is_hidden_and_cant_be_booked(client, db_engine, finished_parent, free_sitter):
    sitter = free_sitter("unwind")
    give(db_engine, sitter["id"], datetime.now(UTC))
    path = f"/parent/sitters/{sitter['id']}"
    assert client.get(path, headers=auth_for(finished_parent)).status_code == 404
    assert client.get(f"{path}/booking-options", headers=auth_for(finished_parent)).status_code == 404
    kids = children_of(db_engine, finished_parent["id"])[:1]
    assert book(client, finished_parent, sitter, child_ids=kids).status_code == 404
    listed = client.get("/parent/sitters", headers=auth_for(finished_parent)).json()
    assert str(sitter["id"]) not in str(listed)

    with db_engine.begin() as conn:  # the block has ended
        conn.execute(
            text("UPDATE sitters SET blocked_until = :t WHERE profile_id = :s"),
            {"t": datetime.now(UTC) - timedelta(minutes=1), "s": sitter["id"]},
        )
    assert client.get(path, headers=auth_for(finished_parent)).status_code == 200


def test_a_blocked_sitter_cant_accept_requests(client, db_engine, finished_parent, free_sitter):
    sitter = free_sitter("unwind")
    made = request(client, db_engine, finished_parent, sitter)
    give(db_engine, sitter["id"], datetime.now(UTC))
    response = answer(client, sitter, made["id"], "accept")
    assert response.status_code == 409 and response.json()["error"]["code"] == "blocked"
    assert answer(client, sitter, made["id"], "decline").status_code == 200  # she can still decline


def test_a_late_cancellation_blocks_her_and_her_other_bookings_stay(client, db_engine, finished_parent, free_sitter):
    sitter = free_sitter("unwind")
    kids = children_of(db_engine, finished_parent["id"])[:1]
    late = book(client, finished_parent, sitter, child_ids=kids).json()
    start = datetime.now(UTC) + timedelta(hours=5)  # cancelled 5 hours before the start: late
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE bookings SET starts_at = :s, ends_at = :e, status = 'confirmed' WHERE id = :b"),
            {"s": start, "e": start + timedelta(hours=2), "b": late["id"]},
        )
    kept = book(client, finished_parent, sitter, child_ids=kids).json()  # another booking with her
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE bookings SET status = 'confirmed' WHERE id = :b"), {"b": kept["id"]})

    response = client.post(f"/sitter/bookings/{late['id']}/cancel", headers=auth_for(sitter))
    assert response.json()["status"] == "cancelled_sitter_late"
    until = blocked_until(db_engine, sitter["id"])
    assert timedelta(hours=23, minutes=59) < until - datetime.now(UTC) <= timedelta(hours=24)
    assert scalar(db_engine, "SELECT status FROM bookings WHERE id = :b", b=kept["id"]) == "confirmed"  # stays (6.6)
    found = their_strikes(client, sitter)
    assert found["counting"] == 1 and found["blocked_until"] is not None
    (strike,) = found["strikes"]
    assert strike["reason"] == "late_cancellation" and strike["booking_id"] == late["id"]


# ---------- admins ----------


def test_admins_add_a_strike_with_a_reason(client, reviewer, db_engine, mailbox, free_sitter):
    sitter = free_sitter("unwind")
    path = f"/admin/sitters/{sitter['id']}/strikes"
    assert client.post(path, json={"reason": "  "}, headers=as_user(reviewer)).status_code == 422
    response = client.post(path, json={"reason": "Rude to a family"}, headers=as_user(reviewer))
    assert response.status_code == 201, response.text
    found = response.json()
    assert found["counting"] == 1 and found["blocked_until"] is not None
    assert found["strikes"][0]["reason"] == "admin" and found["strikes"][0]["note"] == "Rude to a family"
    email = mailbox.sent[-1]
    assert email.to == sitter["email"] and "Rude to a family" in email.body
    audit = row(
        db_engine,
        "SELECT actor_id FROM audit_log WHERE action = 'strike_given' AND entity_id = :s",
        s=found["strikes"][0]["id"],
    )
    assert audit["actor_id"] == reviewer


def test_admins_remove_a_strike_and_her_block_ends(client, reviewer, db_engine, mailbox, free_sitter):
    sitter = free_sitter("unwind")
    give(db_engine, sitter["id"], datetime.now(UTC))
    strike_id = scalar(db_engine, "SELECT id FROM strikes WHERE sitter_id = :s", s=sitter["id"])
    assert (
        client.post(f"/admin/strikes/{strike_id}/remove", json={"reason": ""}, headers=as_user(reviewer)).status_code
        == 422
    )
    response = client.post(
        f"/admin/strikes/{strike_id}/remove", json={"reason": "Doctor's note"}, headers=as_user(reviewer)
    )
    assert response.status_code == 200
    found = response.json()
    assert found["counting"] == 0 and found["blocked_until"] is None
    assert found["strikes"][0]["removal_reason"] == "Doctor's note" and found["strikes"][0]["removed_by"] == str(
        reviewer
    )
    assert blocked_until(db_engine, sitter["id"]) is None
    assert "removed" in mailbox.sent[-1].heading
    again = client.post(f"/admin/strikes/{strike_id}/remove", json={"reason": "x"}, headers=as_user(reviewer))
    assert again.status_code == 409


def test_only_admins_manage_strikes(client, db_engine, finished_parent, free_sitter):
    sitter = free_sitter("unwind")
    path = f"/admin/sitters/{sitter['id']}/strikes"
    assert client.post(path, json={"reason": "x"}, headers=auth_for(sitter)).status_code == 403
    assert client.get(path, headers=auth_for(finished_parent)).status_code == 403
    assert client.get("/sitter/strikes", headers=auth_for(finished_parent)).status_code == 403


# ---------- a doctor's note ----------


def test_she_sends_a_doctors_note_for_a_late_cancellation(client, reviewer, db_engine, storage, free_sitter):
    sitter = free_sitter("unwind")
    give(db_engine, sitter["id"], datetime.now(UTC))
    strike_id = scalar(db_engine, "SELECT id FROM strikes WHERE sitter_id = :s", s=sitter["id"])

    wrong = upload(client, storage, sitter, "government_id")
    response = client.post(
        f"/sitter/strikes/{strike_id}/doctor-note", json={"document_id": wrong}, headers=auth_for(sitter)
    )
    assert response.status_code == 422

    note = upload(client, storage, sitter, "doctor_note")
    response = client.post(
        f"/sitter/strikes/{strike_id}/doctor-note", json={"document_id": note}, headers=auth_for(sitter)
    )
    assert response.status_code == 200, response.text
    assert response.json()["strikes"][0]["doctor_note_sent"] is True
    admin_view = client.get(f"/admin/sitters/{sitter['id']}/strikes", headers=as_user(reviewer)).json()
    assert admin_view["strikes"][0]["doctor_note_document_id"] == note

    other = free_sitter("unwind")
    theirs = client.post(
        f"/sitter/strikes/{strike_id}/doctor-note", json={"document_id": note}, headers=auth_for(other)
    )
    assert theirs.status_code == 404


def test_a_doctors_note_is_only_for_a_late_cancellation(client, db_engine, storage, free_sitter):
    sitter = free_sitter("unwind")
    give(db_engine, sitter["id"], datetime.now(UTC), reason=StrikeReason.admin)
    strike_id = scalar(db_engine, "SELECT id FROM strikes WHERE sitter_id = :s", s=sitter["id"])
    note = upload(client, storage, sitter, "doctor_note")
    response = client.post(
        f"/sitter/strikes/{strike_id}/doctor-note", json={"document_id": note}, headers=auth_for(sitter)
    )
    assert response.status_code == 409
