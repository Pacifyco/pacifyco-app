"""The "finish your profile" checklists (CLAUDE.md 6.13 and 9 "Sign-up flow"): a parent can't book until
theirs is finished; a sitter isn't shown to parents until her profile is finished and approved."""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Profile
from app.services import checklists
from tests.test_documents import (  # noqa: F401  (fixtures)
    accept_consent,
    add_child,
    admin,
    client,
    parent,
    request_upload,
    row,
    rows,
    scalar,
    sitter,
    storage,
)
from tests.test_roles import as_user, make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import auth_for, fill_details, user  # noqa: F401  (fixture)
from tests.test_terms import published
from tests.test_verification import (  # noqa: F401  (fixtures)
    add_references,
    approve_everything,
    psych_attempt,
    review,
    reviewer,
    upload,
)

CONTACTS = [
    {"name": "Priya Rao", "relationship": "Mother", "phone": "9876511111"},
    {"name": "Vikram Rao", "relationship": "Father", "phone": "9876500000"},
]


def checklist(client, who, area):  # noqa: F811
    response = client.get(f"/{area}/checklist", headers=auth_for(who))
    assert response.status_code == 200
    body = response.json()
    return {item["key"]: item["status"] for item in body["items"]}, body


def finished(db_engine, profile_id) -> bool:
    with Session(db_engine) as db:
        return checklists.parent_profile_finished(checklists.parent_checklist(db, db.get(Profile, profile_id)))


def require_finished(db_engine, profile_id) -> None:
    with Session(db_engine) as db:
        checklists.require_finished_parent_profile(db, db.get(Profile, profile_id))


# ---------- parents ----------


def test_a_new_parent_has_everything_to_do(client, parent):  # noqa: F811
    items, body = checklist(client, parent, "parent")
    assert items == {"details": "to_do", "consent": "to_do", "children": "to_do", "emergency_contacts": "to_do"}
    assert body["finished"] is False


def test_a_new_terms_version_reopens_the_consent_step(client, db_engine, parent):  # noqa: F811
    """The terms are ticked on the consent page, so a new version sends the parent back there."""
    accept_consent(client, parent)
    assert checklist(client, parent, "parent")[0]["consent"] == "done"
    with published(db_engine, "privacy_policy", "0.2-test"):
        assert checklist(client, parent, "parent")[0]["consent"] == "to_do"
        new = [{"kind": "privacy_policy", "version": "0.2-test"}]
        assert client.post("/me/terms", json={"accepted": new}, headers=auth_for(parent)).status_code == 200
        assert checklist(client, parent, "parent")[0]["consent"] == "done"


def test_a_parent_cannot_book_until_the_profile_is_finished(client, db_engine, storage, parent):  # noqa: F811
    with pytest.raises(AppError) as refused:
        require_finished(db_engine, parent["id"])
    assert refused.value.code == "profile_unfinished"
    assert refused.value.status_code == 409

    assert fill_details(client, parent).status_code == 200
    accept_consent(client, parent)
    child_id = add_child(db_engine, parent["id"])
    put = client.put("/parent/emergency-contacts", json={"contacts": CONTACTS}, headers=auth_for(parent))
    assert put.status_code == 200
    items, body = checklist(client, parent, "parent")
    assert items == {"details": "done", "consent": "done", "children": "to_do", "emergency_contacts": "done"}
    assert body["finished"] is False  # the child's birth certificate isn't in yet

    upload(client, storage, parent, "birth_certificate", child_id)
    items, body = checklist(client, parent, "parent")
    assert items["children"] == "waiting"
    # Finished: they can book now, but the booking waits for the child to be verified (CLAUDE.md 6.4).
    assert body["finished"] is True
    require_finished(db_engine, parent["id"])


def test_children_status_follows_the_review(client, db_engine, storage, parent, reviewer):  # noqa: F811
    accept_consent(client, parent)
    first = add_child(db_engine, parent["id"])
    upload(client, storage, parent, "birth_certificate", first)
    assert review(client, reviewer, f"/admin/children/{first}/decision").status_code == 200
    assert checklist(client, parent, "parent")[0]["children"] == "approved"  # certificate deleted, still counts

    second = add_child(db_engine, parent["id"])
    upload(client, storage, parent, "birth_certificate", second)
    review(client, reviewer, f"/admin/children/{second}/decision", False, "Unreadable")
    assert checklist(client, parent, "parent")[0]["children"] == "rejected"
    assert finished(db_engine, parent["id"]) is False


def test_consent_comes_first_and_children_say_whats_left(client, db_engine, parent):  # noqa: F811
    # UX review 2026-11-13: consent is step 1; "Your children" says how many and what's needed.
    _, body = checklist(client, parent, "parent")
    assert [item["key"] for item in body["items"]][0] == "consent"
    assert next(item for item in body["items"] if item["key"] == "children")["note"] is None
    accept_consent(client, parent)
    add_child(db_engine, parent["id"])
    _, body = checklist(client, parent, "parent")
    children = next(item for item in body["items"] if item["key"] == "children")
    assert children["status"] == "to_do"
    assert children["note"] == "1 child · certificate needed"


def test_sitters_cannot_see_the_parent_checklist(client, sitter):  # noqa: F811
    assert client.get("/parent/checklist", headers=auth_for(sitter)).status_code == 403


# ---------- sitters ----------


def test_sitter_checklist_moves_from_to_do_to_waiting(client, db_engine, storage, sitter):  # noqa: F811
    items, body = checklist(client, sitter, "sitter")
    assert items == {
        "details": "done",  # the fixture fills them in
        "consent": "to_do",
        "profile": "to_do",
        "identity_documents": "to_do",
        "police_certificate": "to_do",
        "references": "to_do",
        "psych_test": "to_do",
    }
    assert body["live"] is False
    assert [item["key"] for item in body["items"]][:2] == ["consent", "details"]
    profile = next(item for item in body["items"] if item["key"] == "profile")
    assert profile["note"] == "Add your date of birth and a few words about you"  # the exact next action

    upload(client, storage, sitter, "government_id")
    assert checklist(client, sitter, "sitter")[0]["identity_documents"] == "to_do"  # both IDs are needed
    upload(client, storage, sitter, "college_or_work_id")
    upload(client, storage, sitter, "police_certificate")
    add_references(client, sitter)
    psych_attempt(db_engine, sitter["id"], "submitted")
    items, _ = checklist(client, sitter, "sitter")
    assert items["identity_documents"] == items["police_certificate"] == "waiting"
    assert items["references"] == items["psych_test"] == "waiting"


def test_sitter_checklist_shows_reviews_and_going_live(client, db_engine, sitter, reviewer):  # noqa: F811
    approve_everything(client, db_engine, sitter, reviewer)
    client.put(f"/admin/sitters/{sitter['id']}/level", json={"level": "unwind"}, headers=as_user(reviewer))
    items, body = checklist(client, sitter, "sitter")
    assert set(items.values()) == {"done", "approved"}
    assert body["live"] is False  # not until an admin approves her

    assert review(client, reviewer, f"/admin/sitters/{sitter['id']}/decision").status_code == 200
    assert checklist(client, sitter, "sitter")[1]["live"] is True


def test_a_sitter_who_hasnt_accepted_her_consent_cannot_be_approved(client, db_engine, sitter, reviewer):  # noqa: F811
    """Decided 2026-11-12: the sitter consent, Sitter Terms and privacy policy are ticked on her consent
    page, not at sign-up, so approval checks them."""
    approve_everything(client, db_engine, sitter, reviewer)
    client.put(f"/admin/sitters/{sitter['id']}/level", json={"level": "pause"}, headers=as_user(reviewer))
    with db_engine.begin() as conn:  # as if she'd never ticked them
        conn.execute(text("DELETE FROM legal_acceptances WHERE profile_id = :id"), {"id": sitter["id"]})
    assert checklist(client, sitter, "sitter")[0]["consent"] == "to_do"

    response = review(client, reviewer, f"/admin/sitters/{sitter['id']}/decision")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "consent_missing"


def test_a_sitter_without_her_details_cannot_be_approved(client, db_engine, sitter, reviewer):  # noqa: F811
    approve_everything(client, db_engine, sitter, reviewer)
    client.put(f"/admin/sitters/{sitter['id']}/level", json={"level": "pause"}, headers=as_user(reviewer))
    with db_engine.begin() as conn:
        conn.exec_driver_sql("UPDATE profiles SET address = NULL WHERE id = %s", (sitter["id"],))

    response = review(client, reviewer, f"/admin/sitters/{sitter['id']}/decision")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "details_missing"
    assert checklist(client, sitter, "sitter")[0]["details"] == "to_do"


def test_parents_cannot_see_the_sitter_checklist(client, parent):  # noqa: F811
    assert client.get("/sitter/checklist", headers=auth_for(parent)).status_code == 403
