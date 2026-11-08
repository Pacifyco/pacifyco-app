"""The admin verification queue (CLAUDE.md 7 and 9): admins review each sitter onboarding step, her
references and psychology test, set her level and approve her; she isn't live until every step passes
and a level is set. Families: an admin approves each child's birth certificate, which is then deleted
(keeping status, verifier and date). Health disclosure views are logged; every decision is audited."""

import uuid

import pytest
from sqlalchemy import text

from app.models import OnboardingStatus, Profile, ProfileStatus, Sitter, SitterLevel
from app.services.verification import is_live
from tests.test_documents import (  # noqa: F401  (fixtures)
    PDF,
    accept_consent,
    add_child,
    admin,
    client,
    other_parent,
    parent,
    request_upload,
    row,
    rows,
    scalar,
    sitter,
    storage,
)
from tests.test_roles import as_user, make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import auth_for, user  # noqa: F401  (fixture)

DOCUMENT_STEPS = ("profile", "identity_documents", "police_certificate")


@pytest.fixture
def reviewer(admin, db_engine):  # noqa: F811
    """The admin, plus clean-up of the audit rows they write (audit_log is append-only for the API)."""
    yield admin
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM audit_log WHERE actor_id = :id"), {"id": admin})


def upload(client, storage, owner, doc_type, child_id=None):  # noqa: F811
    ticket = request_upload(client, owner, doc_type, child_id).json()
    path = f"{owner['id']}/{ticket['document_id']}"
    storage.put(path, PDF)
    assert client.post(f"/documents/{ticket['document_id']}/confirm", headers=auth_for(owner)).status_code == 200
    return ticket["document_id"]


def add_references(client, sitter_user):  # noqa: F811
    for name in ("Asha Rao", "Meera Iyer"):
        body = {"name": name, "phone": "9876543210", "relationship": "Former employer"}
        assert client.post("/sitter/references", json=body, headers=auth_for(sitter_user)).status_code == 201
    return client.get("/sitter/references", headers=auth_for(sitter_user)).json()


def psych_attempt(db_engine, sitter_id, status):
    with db_engine.begin() as conn:
        test_id = conn.execute(text("SELECT id FROM psych_tests WHERE is_active LIMIT 1")).scalar_one()
        conn.execute(
            text("INSERT INTO psych_attempts (sitter_id, test_id, status) VALUES (:s, :t, :st)"),
            {"s": sitter_id, "t": test_id, "st": status},
        )


def review(client, admin_id, path, approved=True, notes=None, reason=None):  # noqa: F811
    """A decision. Rejecting needs a reason shown to the person; by default the notes double as one."""
    if not approved and reason is None:
        reason = notes or "Please upload a clearer copy"
    body = {"approved": approved, "notes": notes, "rejection_reason": reason}
    return client.post(path, json=body, headers=as_user(admin_id))


def approve_everything(client, db_engine, sitter_user, admin_id):  # noqa: F811
    sitter_id = sitter_user["id"]
    for step in DOCUMENT_STEPS:
        assert review(client, admin_id, f"/admin/sitters/{sitter_id}/steps/{step}").status_code == 200
    for reference in add_references(client, sitter_user):
        assert review(client, admin_id, f"/admin/references/{reference['id']}/decision").status_code == 200
    psych_attempt(db_engine, sitter_id, "passed")


def audit_actions(db_engine, admin_id):
    return [r["action"] for r in rows(db_engine, "SELECT action FROM audit_log WHERE actor_id = :id", id=admin_id)]


# ---------- the queue ----------


def test_queue(client, db_engine, storage, parent, other_parent, sitter, reviewer):  # noqa: F811
    """Sitters in onboarding, and families with a child whose birth certificate is uploaded."""
    accept_consent(client, parent)
    child_id = add_child(db_engine, parent["id"])
    upload(client, storage, parent, "birth_certificate", child_id)
    add_child(db_engine, other_parent["id"])  # a child with no certificate yet: nothing to review

    queue = client.get("/admin/verifications", headers=as_user(reviewer)).json()

    sitter_item = next(item for item in queue["sitters"] if item["id"] == str(sitter["id"]))
    assert sitter_item["steps_approved"] == 0
    assert sitter_item["steps_total"] == 5
    assert sitter_item["level"] is None
    family_ids = {item["id"]: item for item in queue["families"]}
    assert family_ids[str(parent["id"])]["children_to_review"] == 1
    assert str(other_parent["id"]) not in family_ids


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/admin/verifications"),
        ("get", "/admin/sitters/{id}"),
        ("get", "/admin/sitters/{id}/health-disclosure"),
        ("post", "/admin/sitters/{id}/decision"),
        ("put", "/admin/sitters/{id}/level"),
        ("get", "/admin/parents/{id}"),
        ("post", "/admin/children/{id}/decision"),
    ],
)
def test_parents_and_sitters_cannot_use_the_queue(client, parent, sitter, method, path):  # noqa: F811
    for caller in (parent, sitter):
        response = client.request(method, path.format(id=sitter["id"]), json={}, headers=auth_for(caller))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"


def test_unknown_ids_are_404(client, reviewer):  # noqa: F811
    missing = uuid.uuid4()
    assert client.get(f"/admin/sitters/{missing}", headers=as_user(reviewer)).status_code == 404
    assert client.get(f"/admin/parents/{missing}", headers=as_user(reviewer)).status_code == 404
    assert review(client, reviewer, f"/admin/references/{missing}/decision").status_code == 404
    assert review(client, reviewer, f"/admin/children/{missing}/decision").status_code == 404
    assert review(client, reviewer, f"/admin/sitters/{missing}/steps/profile").status_code == 404


# ---------- sitter steps ----------


def test_a_new_sitter_has_every_step_pending(client, sitter, reviewer):  # noqa: F811
    body = client.get(f"/admin/sitters/{sitter['id']}", headers=as_user(reviewer)).json()
    assert body["steps"] == {
        "profile": "pending",
        "identity_documents": "pending",
        "police_certificate": "pending",
        "references": "pending",
        "psych_test": "pending",
    }
    assert body["onboarding_status"] == "in_progress"
    assert body["psych_attempt"] is None


def test_review_shows_her_uploaded_documents_only(client, storage, sitter, reviewer):  # noqa: F811
    document_id = upload(client, storage, sitter, "police_certificate")
    request_upload(client, sitter, "government_id")  # requested but never uploaded
    body = client.get(f"/admin/sitters/{sitter['id']}", headers=as_user(reviewer)).json()
    assert [(d["id"], d["type"]) for d in body["documents"]] == [(document_id, "police_certificate")]


def test_reviewing_a_step_is_stored_and_audited(client, db_engine, sitter, reviewer):  # noqa: F811
    response = review(client, reviewer, f"/admin/sitters/{sitter['id']}/steps/police_certificate", False, "Blurry")
    assert response.json() == {"status": "rejected"}
    response = review(client, reviewer, f"/admin/sitters/{sitter['id']}/steps/police_certificate", True)
    assert response.json() == {"status": "approved"}

    stored = row(db_engine, "SELECT status, reviewed_by FROM onboarding_steps WHERE sitter_id = :id", id=sitter["id"])
    assert stored["status"] == "approved"
    assert stored["reviewed_by"] == reviewer
    assert audit_actions(db_engine, reviewer) == ["onboarding_step_reviewed", "onboarding_step_reviewed"]


def test_an_unknown_step_is_refused(client, sitter, reviewer):  # noqa: F811
    assert review(client, reviewer, f"/admin/sitters/{sitter['id']}/steps/interview").status_code == 422


def test_references_pass_only_when_both_are_approved(client, sitter, reviewer):  # noqa: F811
    first, second = add_references(client, sitter)

    def references_step():
        return client.get(f"/admin/sitters/{sitter['id']}", headers=as_user(reviewer)).json()["steps"]["references"]

    review(client, reviewer, f"/admin/references/{first['id']}/decision")
    assert references_step() == "pending"
    review(client, reviewer, f"/admin/references/{second['id']}/decision", False, "Didn't answer")
    assert references_step() == "rejected"
    review(client, reviewer, f"/admin/references/{second['id']}/decision")
    assert references_step() == "approved"


@pytest.mark.parametrize(
    ("attempt_status", "step"),
    [("in_progress", "pending"), ("submitted", "pending"), ("passed", "approved"), ("failed", "rejected")],
)
def test_psych_test_step_follows_her_latest_attempt(client, db_engine, sitter, reviewer, attempt_status, step):  # noqa: F811
    psych_attempt(db_engine, sitter["id"], attempt_status)
    body = client.get(f"/admin/sitters/{sitter['id']}", headers=as_user(reviewer)).json()
    assert body["steps"]["psych_test"] == step
    assert body["psych_attempt"]["status"] == attempt_status


def test_setting_her_level_is_audited(client, db_engine, sitter, reviewer):  # noqa: F811
    response = client.put(f"/admin/sitters/{sitter['id']}/level", json={"level": "unwind"}, headers=as_user(reviewer))
    assert response.json() == {"level": "unwind"}
    assert scalar(db_engine, "SELECT level FROM sitters WHERE profile_id = :id", id=sitter["id"]) == "unwind"
    assert audit_actions(db_engine, reviewer) == ["sitter_level_set"]


def test_an_unknown_level_is_refused(client, sitter, reviewer):  # noqa: F811
    response = client.put(f"/admin/sitters/{sitter['id']}/level", json={"level": "gold"}, headers=as_user(reviewer))
    assert response.status_code == 422


# ---------- approving a sitter (CLAUDE.md 9: not live until every step passes and a level is set) ----------


def test_approval_is_refused_until_every_step_passes(client, sitter, reviewer):  # noqa: F811
    review(client, reviewer, f"/admin/sitters/{sitter['id']}/steps/profile")
    response = review(client, reviewer, f"/admin/sitters/{sitter['id']}/decision")
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "steps_not_approved"
    assert error["details"]["steps"] == ["identity_documents", "police_certificate", "references", "psych_test"]


def test_approval_is_refused_without_a_level(client, db_engine, sitter, reviewer):  # noqa: F811
    approve_everything(client, db_engine, sitter, reviewer)
    response = review(client, reviewer, f"/admin/sitters/{sitter['id']}/decision")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "level_not_set"


def test_approving_makes_her_live(client, db_engine, sitter, reviewer):  # noqa: F811
    approve_everything(client, db_engine, sitter, reviewer)
    client.put(f"/admin/sitters/{sitter['id']}/level", json={"level": "pause"}, headers=as_user(reviewer))

    response = review(client, reviewer, f"/admin/sitters/{sitter['id']}/decision")
    assert response.json() == {"onboarding_status": "approved"}
    assert scalar(db_engine, "SELECT status FROM profiles WHERE id = :id", id=sitter["id"]) == "active"
    assert "sitter_approved" in audit_actions(db_engine, reviewer)
    queue = client.get("/admin/verifications", headers=as_user(reviewer)).json()
    assert str(sitter["id"]) not in {item["id"] for item in queue["sitters"]}


def test_approving_never_reinstates_a_suspended_account(client, db_engine, sitter, reviewer):  # noqa: F811
    approve_everything(client, db_engine, sitter, reviewer)
    client.put(f"/admin/sitters/{sitter['id']}/level", json={"level": "pause"}, headers=as_user(reviewer))
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE profiles SET status = 'suspended' WHERE id = :id"), {"id": sitter["id"]})
    assert review(client, reviewer, f"/admin/sitters/{sitter['id']}/decision").status_code == 200
    assert scalar(db_engine, "SELECT status FROM profiles WHERE id = :id", id=sitter["id"]) == "suspended"


def test_rejecting_a_sitter(client, db_engine, sitter, reviewer):  # noqa: F811
    response = review(client, reviewer, f"/admin/sitters/{sitter['id']}/decision", False, "Police certificate fake")
    assert response.json() == {"onboarding_status": "rejected"}
    assert scalar(db_engine, "SELECT status FROM profiles WHERE id = :id", id=sitter["id"]) == "pending"
    assert audit_actions(db_engine, reviewer) == ["sitter_rejected"]


@pytest.mark.parametrize(
    ("profile_status", "onboarding", "level", "live"),
    [
        (ProfileStatus.active, OnboardingStatus.approved, SitterLevel.pause, True),
        (ProfileStatus.active, OnboardingStatus.approved, None, False),
        (ProfileStatus.active, OnboardingStatus.in_progress, SitterLevel.pause, False),
        (ProfileStatus.suspended, OnboardingStatus.approved, SitterLevel.pause, False),
        (ProfileStatus.pending, OnboardingStatus.approved, SitterLevel.pause, False),
    ],
)
def test_is_live(profile_status, onboarding, level, live):
    profile = Profile(status=profile_status)
    sitter_row = Sitter(onboarding_status=onboarding, level=level)
    assert is_live(profile, sitter_row) is live


# ---------- health disclosure (admin-only, every view logged) ----------


def test_viewing_the_health_disclosure_is_logged(client, db_engine, sitter, reviewer):  # noqa: F811
    client.put("/sitter/health-disclosure", json={"disclosure": "Mild asthma"}, headers=auth_for(sitter))
    review_body = client.get(f"/admin/sitters/{sitter['id']}", headers=as_user(reviewer)).json()
    assert review_body["has_health_disclosure"] is True
    assert "Mild asthma" not in str(review_body)  # never in the general review

    response = client.get(f"/admin/sitters/{sitter['id']}/health-disclosure", headers=as_user(reviewer))
    assert response.json() == {"disclosure": "Mild asthma"}
    logged = rows(db_engine, "SELECT action, entity_id FROM audit_log WHERE actor_id = :id", id=reviewer)
    assert [dict(r) for r in logged] == [{"action": "health_disclosure_viewed", "entity_id": str(sitter["id"])}]


# ---------- families: birth certificates ----------


def family_with_certificate(client, db_engine, storage, parent_user):  # noqa: F811
    accept_consent(client, parent_user)
    child_id = add_child(db_engine, parent_user["id"])
    document_id = upload(client, storage, parent_user, "birth_certificate", child_id)
    return child_id, document_id


def test_family_review_shows_children_and_their_certificates(client, db_engine, storage, parent, reviewer):  # noqa: F811
    child_id, document_id = family_with_certificate(client, db_engine, storage, parent)
    body = client.get(f"/admin/parents/{parent['id']}", headers=as_user(reviewer)).json()
    assert body["verification_status"] == "pending"
    [child] = body["children"]
    assert child["id"] == str(child_id)
    assert [doc["id"] for doc in child["birth_certificates"]] == [document_id]


def test_approving_a_child_deletes_the_birth_certificate(client, db_engine, storage, parent, reviewer):  # noqa: F811
    child_id, document_id = family_with_certificate(client, db_engine, storage, parent)
    path = f"{parent['id']}/{document_id}"

    response = review(client, reviewer, f"/admin/children/{child_id}/decision")
    assert response.json() == {"status": "approved"}

    assert path in storage.deleted
    assert row(db_engine, "SELECT deleted_at FROM documents WHERE id = :id", id=document_id)["deleted_at"] is not None
    child = row(
        db_engine, "SELECT verification_status, verified_by, verified_at FROM children WHERE id = :id", id=child_id
    )
    assert child["verification_status"] == "approved"
    assert child["verified_by"] == reviewer  # status, verifier and date are kept
    assert child["verified_at"] is not None
    # and it can't be viewed any more
    assert client.get(f"/admin/documents/{document_id}/view-url", headers=as_user(reviewer)).status_code == 404
    assert (
        client.get(f"/admin/parents/{parent['id']}", headers=as_user(reviewer)).json()["children"][0][
            "birth_certificates"
        ]
        == []
    )


def test_approving_a_child_verifies_the_parent(client, db_engine, storage, parent, reviewer):  # noqa: F811
    child_id, _ = family_with_certificate(client, db_engine, storage, parent)
    review(client, reviewer, f"/admin/children/{child_id}/decision")
    assert scalar(db_engine, "SELECT verification_status FROM parents WHERE profile_id = :id", id=parent["id"]) == (
        "approved"
    )
    assert scalar(db_engine, "SELECT status FROM profiles WHERE id = :id", id=parent["id"]) == "active"
    assert audit_actions(db_engine, reviewer) == ["child_verified", "parent_verified"]


def test_a_family_is_verified_only_once_every_child_is_approved(client, db_engine, storage, parent, reviewer):  # noqa: F811
    first, _ = family_with_certificate(client, db_engine, storage, parent)
    second = add_child(db_engine, parent["id"])
    upload(client, storage, parent, "birth_certificate", second)

    review(client, reviewer, f"/admin/children/{first}/decision")
    status = "SELECT verification_status FROM parents WHERE profile_id = :id"
    assert scalar(db_engine, status, id=parent["id"]) == "pending"

    review(client, reviewer, f"/admin/children/{second}/decision")
    assert scalar(db_engine, status, id=parent["id"]) == "approved"


def test_a_verified_family_can_add_a_child_and_waits_for_its_certificate(client, db_engine, storage, parent, reviewer):  # noqa: F811
    first, _ = family_with_certificate(client, db_engine, storage, parent)
    review(client, reviewer, f"/admin/children/{first}/decision")

    response = client.post(
        "/parent/children", json={"name": "Kabir", "date_of_birth": "2022-05-01"}, headers=auth_for(parent)
    )
    assert response.status_code in (200, 201)
    assert scalar(db_engine, "SELECT verification_status FROM parents WHERE profile_id = :id", id=parent["id"]) == (
        "pending"
    )
    assert scalar(db_engine, "SELECT verification_status FROM children WHERE id = :id", id=first) == "approved"
    try:
        reset = rows(db_engine, "SELECT actor_id FROM audit_log WHERE action = 'parent_verification_reset'")
        assert [r["actor_id"] for r in reset] == [parent["id"]]
    finally:  # the parent wrote this audit row; remove it so the parent can be cleaned up
        with db_engine.begin() as conn:
            conn.execute(text("DELETE FROM audit_log WHERE actor_id = :id"), {"id": parent["id"]})


def test_a_child_cannot_be_approved_without_a_certificate(client, db_engine, parent, reviewer):  # noqa: F811
    child_id = add_child(db_engine, parent["id"])
    response = review(client, reviewer, f"/admin/children/{child_id}/decision")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_birth_certificate"


def test_a_rejected_child_goes_back_for_review_after_a_new_upload(client, db_engine, storage, parent, reviewer):  # noqa: F811
    child_id, document_id = family_with_certificate(client, db_engine, storage, parent)
    assert review(client, reviewer, f"/admin/children/{child_id}/decision", False, "Name doesn't match").json() == {
        "status": "rejected"
    }
    assert f"{parent['id']}/{document_id}" not in storage.deleted  # only approval deletes it
    assert scalar(db_engine, "SELECT verification_status FROM parents WHERE profile_id = :id", id=parent["id"]) == (
        "pending"
    )

    upload(client, storage, parent, "birth_certificate", child_id)
    assert scalar(db_engine, "SELECT verification_status FROM children WHERE id = :id", id=child_id) == "pending"


def test_a_verified_childs_name_and_birth_date_are_locked(client, db_engine, storage, parent, reviewer):  # noqa: F811
    child_id, _ = family_with_certificate(client, db_engine, storage, parent)
    review(client, reviewer, f"/admin/children/{child_id}/decision")
    base = {"name": "Asha", "date_of_birth": "2023-01-01", "allergies": None, "medical_notes": None, "routines": None}

    changed = client.put(
        f"/parent/children/{child_id}", json={**base, "date_of_birth": "2024-01-01"}, headers=auth_for(parent)
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "child_verified"
    allowed = client.put(
        f"/parent/children/{child_id}", json={**base, "allergies": "Peanuts"}, headers=auth_for(parent)
    )
    assert allowed.status_code == 200
