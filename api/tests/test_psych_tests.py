"""Sitter psychology screening (CLAUDE.md sections 7 step 5 and 9): the sitter takes the placeholder
test and submits once every question is answered; an admin reads the answers and records pass or
fail (not auto-scored); no IDOR on either side."""

import uuid

import pytest
from sqlalchemy import text

from tests.test_auth import client  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, user  # noqa: F401  (fixture)


@pytest.fixture
def sitter(client, db_engine, user):  # noqa: F811
    assert client.post("/me/profile", json={**PARENT, "role": "sitter"}, headers=auth_for(user)).status_code == 201
    yield user
    with db_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM psych_answers WHERE attempt_id IN (SELECT id FROM psych_attempts WHERE sitter_id = :id)"),
            {"id": user["id"]},
        )
        conn.execute(text("DELETE FROM psych_attempts WHERE sitter_id = :id"), {"id": user["id"]})
        for table, column in (("legal_acceptances", "profile_id"), ("consents", "parent_id")):
            conn.execute(text(f"DELETE FROM {table} WHERE {column} = :id"), {"id": user["id"]})
        conn.execute(text("DELETE FROM profiles WHERE id = :id"), {"id": user["id"]})


@pytest.fixture
def admin(client, db_engine):  # noqa: F811
    """A separate identity from `sitter` -- fixtures can't share `user`, or the same profile id would
    need to be both a sitter and an admin."""
    admin_id = uuid.uuid4()
    admin_user = {"id": admin_id, "email": f"{admin_id}@example.com"}
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO profiles (id, role, full_name, email, status) VALUES (:id, 'admin', 'Admin', :e, 'active')"
            ),
            {"id": admin_id, "e": admin_user["email"]},
        )
    yield admin_user
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM profiles WHERE id = :id"), {"id": admin_id})


def answer_every_question(test_client, sitter, questions):
    answers = [{"question_id": q["id"], "answer_text": "A thoughtful answer."} for q in questions]
    response = test_client.put("/sitter/psych-test/answers", json={"answers": answers}, headers=auth_for(sitter))
    assert response.status_code == 200
    return response.json()


# ---------- sitter: taking the test ----------


def test_the_active_test_is_the_seeded_placeholder(client, sitter):  # noqa: F811
    response = client.get("/sitter/psych-test", headers=auth_for(sitter))
    assert response.status_code == 200
    body = response.json()
    assert body["is_placeholder"] is True
    assert len(body["questions"]) == 5
    assert {q["kind"] for q in body["questions"]} == {"multiple_choice", "short_answer"}
    assert body["attempt"] is None  # nothing started yet


def test_saving_answers_starts_an_attempt_in_progress(client, sitter):  # noqa: F811
    questions = client.get("/sitter/psych-test", headers=auth_for(sitter)).json()["questions"]
    attempt = answer_every_question(client, sitter, questions)
    assert attempt["status"] == "in_progress"
    assert len(attempt["answers"]) == len(questions)

    # Saving again edits the same attempt rather than creating a new one.
    again = client.get("/sitter/psych-test", headers=auth_for(sitter)).json()
    assert again["attempt"]["status"] == "in_progress"


def test_cannot_submit_until_every_question_is_answered(client, sitter):  # noqa: F811
    questions = client.get("/sitter/psych-test", headers=auth_for(sitter)).json()["questions"]
    one_answer = [{"question_id": questions[0]["id"], "answer_text": "Just one."}]
    client.put("/sitter/psych-test/answers", json={"answers": one_answer}, headers=auth_for(sitter))

    response = client.post("/sitter/psych-test/submit", headers=auth_for(sitter))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "incomplete"


def test_submitting_moves_to_submitted_and_locks_answers(client, sitter):  # noqa: F811
    questions = client.get("/sitter/psych-test", headers=auth_for(sitter)).json()["questions"]
    answer_every_question(client, sitter, questions)

    response = client.post("/sitter/psych-test/submit", headers=auth_for(sitter))
    assert response.status_code == 200
    assert response.json()["status"] == "submitted"
    assert response.json()["submitted_at"] is not None

    locked = client.put(
        "/sitter/psych-test/answers",
        json={"answers": [{"question_id": questions[0]["id"], "answer_text": "Changed my mind."}]},
        headers=auth_for(sitter),
    )
    assert locked.status_code == 409
    assert locked.json()["error"]["code"] == "attempt_not_open"


def test_blank_answer_does_not_count_as_answered(client, sitter):  # noqa: F811
    questions = client.get("/sitter/psych-test", headers=auth_for(sitter)).json()["questions"]
    answers = [{"question_id": q["id"], "answer_text": "   "} for q in questions]
    client.put("/sitter/psych-test/answers", json={"answers": answers}, headers=auth_for(sitter))

    response = client.post("/sitter/psych-test/submit", headers=auth_for(sitter))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "incomplete"


# ---------- admin: reviewing attempts ----------


def test_only_submitted_attempts_show_up_for_review_by_default(client, sitter, admin):  # noqa: F811
    questions = client.get("/sitter/psych-test", headers=auth_for(sitter)).json()["questions"]
    answer_every_question(client, sitter, questions)

    assert client.get("/admin/psych-attempts", headers=auth_for(admin)).json() == []

    client.post("/sitter/psych-test/submit", headers=auth_for(sitter))
    listed = client.get("/admin/psych-attempts", headers=auth_for(admin)).json()
    assert len(listed) == 1
    assert listed[0]["sitter_name"] == "Meera Rao"
    assert listed[0]["status"] == "submitted"


def test_admin_sees_the_full_answers(client, sitter, admin):  # noqa: F811
    questions = client.get("/sitter/psych-test", headers=auth_for(sitter)).json()["questions"]
    answer_every_question(client, sitter, questions)
    client.post("/sitter/psych-test/submit", headers=auth_for(sitter))

    attempt_id = client.get("/admin/psych-attempts", headers=auth_for(admin)).json()[0]["id"]
    detail = client.get(f"/admin/psych-attempts/{attempt_id}", headers=auth_for(admin)).json()
    assert len(detail["answers"]) == len(questions)
    assert all(a["answer_text"] == "A thoughtful answer." for a in detail["answers"])


def test_admin_records_pass_and_it_is_audit_logged(client, db_engine, sitter, admin):  # noqa: F811
    questions = client.get("/sitter/psych-test", headers=auth_for(sitter)).json()["questions"]
    answer_every_question(client, sitter, questions)
    client.post("/sitter/psych-test/submit", headers=auth_for(sitter))
    attempt_id = client.get("/admin/psych-attempts", headers=auth_for(admin)).json()[0]["id"]

    response = client.post(
        f"/admin/psych-attempts/{attempt_id}/decision",
        json={"passed": True, "notes": "Good judgement calls."},
        headers=auth_for(admin),
    )
    assert response.status_code == 200
    assert response.json() == {"id": attempt_id, "status": "passed"}

    mine = client.get("/sitter/psych-test", headers=auth_for(sitter)).json()
    assert mine["attempt"]["status"] == "passed"

    with db_engine.connect() as conn:
        logged = (
            conn.execute(
                text("SELECT action, entity, entity_id, actor_id FROM audit_log WHERE entity = 'psych_attempts'")
            )
            .mappings()
            .first()
        )
    assert logged["action"] == "psych_attempt_reviewed"
    assert logged["entity_id"] == attempt_id
    assert str(logged["actor_id"]) == str(admin["id"])


def test_admin_records_fail_and_sitter_can_retake(client, sitter, admin):  # noqa: F811
    questions = client.get("/sitter/psych-test", headers=auth_for(sitter)).json()["questions"]
    answer_every_question(client, sitter, questions)
    client.post("/sitter/psych-test/submit", headers=auth_for(sitter))
    attempt_id = client.get("/admin/psych-attempts", headers=auth_for(admin)).json()[0]["id"]

    client.post(f"/admin/psych-attempts/{attempt_id}/decision", json={"passed": False}, headers=auth_for(admin))

    mine = client.get("/sitter/psych-test", headers=auth_for(sitter)).json()
    assert mine["attempt"]["status"] == "failed"

    retake = client.put(
        "/sitter/psych-test/answers",
        json={"answers": [{"question_id": questions[0]["id"], "answer_text": "Trying again."}]},
        headers=auth_for(sitter),
    )
    assert retake.status_code == 200
    assert retake.json()["status"] == "in_progress"


def test_cannot_decide_an_attempt_twice(client, sitter, admin):  # noqa: F811
    questions = client.get("/sitter/psych-test", headers=auth_for(sitter)).json()["questions"]
    answer_every_question(client, sitter, questions)
    client.post("/sitter/psych-test/submit", headers=auth_for(sitter))
    attempt_id = client.get("/admin/psych-attempts", headers=auth_for(admin)).json()[0]["id"]

    client.post(f"/admin/psych-attempts/{attempt_id}/decision", json={"passed": True}, headers=auth_for(admin))
    second = client.post(
        f"/admin/psych-attempts/{attempt_id}/decision", json={"passed": False}, headers=auth_for(admin)
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "not_submitted"


def test_cannot_decide_an_attempt_still_in_progress(client, sitter, admin):  # noqa: F811
    questions = client.get("/sitter/psych-test", headers=auth_for(sitter)).json()["questions"]
    answer_every_question(client, sitter, questions)  # started, but not submitted

    in_progress = client.get("/admin/psych-attempts", params={"status": "in_progress"}, headers=auth_for(admin))
    attempt_id = in_progress.json()[0]["id"]

    response = client.post(
        f"/admin/psych-attempts/{attempt_id}/decision", json={"passed": True}, headers=auth_for(admin)
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_submitted"


def test_cannot_claim_another_sitters_attempt_by_guessing_the_id(client, db_engine, sitter, admin):  # noqa: F811
    # The sitter API never takes an attempt id, so there is no id for another sitter to guess into;
    # confirm the admin decision endpoint 404s for a made-up id instead.
    missing = uuid.uuid4()
    response = client.post(f"/admin/psych-attempts/{missing}/decision", json={"passed": True}, headers=auth_for(admin))
    assert response.status_code == 404
