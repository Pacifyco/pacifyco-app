"""Onboarding polish (decided 2026-11-09): a reason is required to reject and is shown to the parent or
sitter; changing a rejected sitter step sends it back for review (the psych test needs an admin
instead); sitters upload a profile photo, which parents see only while she's live."""

import pytest

from tests.test_documents import (  # noqa: F401  (fixtures)
    JPEG,
    PDF,
    accept_consent,
    add_child,
    admin,
    client,
    parent,
    request_upload,
    scalar,
    sitter,
    storage,
)
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_roles import as_user, make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import auth_for, user  # noqa: F401  (fixture)
from tests.test_sitters import PROFILE_BODY
from tests.test_verification import add_references, psych_attempt, review, reviewer, upload  # noqa: F401


def upload_bytes(client, storage, owner, doc_type, data):  # noqa: F811
    ticket = request_upload(client, owner, doc_type).json()
    storage.put(f"{owner['id']}/{ticket['document_id']}", data)
    return client.post(f"/documents/{ticket['document_id']}/confirm", headers=auth_for(owner))


def checklist(client, who, area):  # noqa: F811
    body = client.get(f"/{area}/checklist", headers=auth_for(who)).json()
    return {item["key"]: item for item in body["items"]}, body


# ---------- a reason is required to reject ----------


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_rejecting_needs_a_reason(client, sitter, reviewer, reason):  # noqa: F811
    response = client.post(
        f"/admin/sitters/{sitter['id']}/steps/police_certificate",
        json={"approved": False, "notes": "internal", "rejection_reason": reason},
        headers=as_user(reviewer),
    )
    assert response.status_code == 422


def test_failing_the_psych_test_needs_a_reason(client, db_engine, sitter, reviewer):  # noqa: F811
    psych_attempt(db_engine, sitter["id"], "submitted")
    attempt_id = scalar(db_engine, "SELECT id FROM psych_attempts WHERE sitter_id = :id", id=sitter["id"])
    path = f"/admin/psych-attempts/{attempt_id}/decision"
    assert client.post(path, json={"passed": False}, headers=as_user(reviewer)).status_code == 422
    ok = client.post(path, json={"passed": False, "rejection_reason": "Too brief"}, headers=as_user(reviewer))
    assert ok.status_code == 200
    items, _ = checklist(client, sitter, "sitter")
    assert items["psych_test"] == {"key": "psych_test", "status": "rejected", "reason": "Too brief"}


# ---------- parents see why ----------


def test_a_parent_sees_why_a_birth_certificate_was_rejected(client, db_engine, storage, parent, reviewer):  # noqa: F811
    accept_consent(client, parent)
    child_id = add_child(db_engine, parent["id"])
    upload(client, storage, parent, "birth_certificate", child_id)
    review(client, reviewer, f"/admin/children/{child_id}/decision", False, "blurry", "The photo is too blurry")

    [child] = client.get("/parent/children", headers=auth_for(parent)).json()
    assert child["verification_status"] == "rejected"
    assert child["rejection_reason"] == "The photo is too blurry"
    items, _ = checklist(client, parent, "parent")
    assert items["children"]["reason"] == "Asha: The photo is too blurry"

    # A new certificate goes back for review and the old reason goes away.
    upload(client, storage, parent, "birth_certificate", child_id)
    [child] = client.get("/parent/children", headers=auth_for(parent)).json()
    assert (child["verification_status"], child["rejection_reason"]) == ("pending", None)


# ---------- sitters see why, and changes go back for review ----------


def test_a_rejected_document_step_goes_back_for_review_on_a_new_upload(client, storage, sitter, reviewer):  # noqa: F811
    path = f"/admin/sitters/{sitter['id']}/steps/identity_documents"
    review(client, reviewer, path, False, reason="Your ID has expired")
    items, _ = checklist(client, sitter, "sitter")
    assert items["identity_documents"]["status"] == "rejected"
    assert items["identity_documents"]["reason"] == "Your ID has expired"

    upload(client, storage, sitter, "government_id")
    items, _ = checklist(client, sitter, "sitter")
    assert items["identity_documents"]["reason"] is None
    assert items["identity_documents"]["status"] == "to_do"  # both IDs still needed; no longer rejected
    review_page = client.get(f"/admin/sitters/{sitter['id']}", headers=as_user(reviewer)).json()
    assert review_page["steps"]["identity_documents"] == "pending"


def test_a_rejected_profile_goes_back_for_review_when_she_edits_it(client, sitter, reviewer):  # noqa: F811
    review(
        client, reviewer, f"/admin/sitters/{sitter['id']}/steps/profile", False, reason="Please add more to your bio"
    )
    assert client.put("/sitter/profile", json=PROFILE_BODY, headers=auth_for(sitter)).status_code == 200
    review_page = client.get(f"/admin/sitters/{sitter['id']}", headers=as_user(reviewer)).json()
    assert review_page["steps"]["profile"] == "pending"


def test_an_approved_step_stays_approved_when_she_uploads_again(client, storage, sitter, reviewer):  # noqa: F811
    review(client, reviewer, f"/admin/sitters/{sitter['id']}/steps/police_certificate")
    upload(client, storage, sitter, "police_certificate")
    review_page = client.get(f"/admin/sitters/{sitter['id']}", headers=as_user(reviewer)).json()
    assert review_page["steps"]["police_certificate"] == "approved"


def test_a_sitter_sees_which_reference_was_rejected_and_why(client, sitter, reviewer):  # noqa: F811
    first, _ = add_references(client, sitter)
    review(client, reviewer, f"/admin/references/{first['id']}/decision", False, reason="We couldn't reach them")
    mine = {ref["name"]: ref for ref in client.get("/sitter/references", headers=auth_for(sitter)).json()}
    assert mine[first["name"]]["rejection_reason"] == "We couldn't reach them"
    items, _ = checklist(client, sitter, "sitter")
    assert items["references"]["reason"] == f"{first['name']}: We couldn't reach them"

    # Removing the rejected reference and adding another sends the step back for review.
    client.delete(f"/sitter/references/{first['id']}", headers=auth_for(sitter))
    client.post(
        "/sitter/references",
        json={"name": "Ravi Kumar", "phone": "9876511111", "relationship": "Neighbour"},
        headers=auth_for(sitter),
    )
    assert checklist(client, sitter, "sitter")[0]["references"]["status"] == "waiting"


def test_a_rejected_application_tells_her_why(client, sitter, reviewer):  # noqa: F811
    review(client, reviewer, f"/admin/sitters/{sitter['id']}/decision", False, reason="We can't take new sitters yet")
    _, body = checklist(client, sitter, "sitter")
    assert body["application_rejected_reason"] == "We can't take new sitters yet"


def test_approving_clears_the_reason(client, sitter, reviewer):  # noqa: F811
    path = f"/admin/sitters/{sitter['id']}/steps/police_certificate"
    review(client, reviewer, path, False, reason="Too old")
    review(client, reviewer, path)
    items, _ = checklist(client, sitter, "sitter")
    assert items["police_certificate"] == {"key": "police_certificate", "status": "approved", "reason": None}


# ---------- profile photos ----------


def test_a_photo_must_be_a_jpg_or_png(client, storage, sitter):  # noqa: F811
    refused = upload_bytes(client, storage, sitter, "photo", PDF)
    assert refused.status_code == 422
    assert refused.json()["error"]["message"] == "Please upload your photo as a JPG or PNG"
    assert upload_bytes(client, storage, sitter, "photo", JPEG).status_code == 200


def test_the_application_step_needs_a_photo(client, storage, sitter):  # noqa: F811
    client.put("/sitter/profile", json=PROFILE_BODY, headers=auth_for(sitter))
    client.put("/sitter/payout-details", json={"method": "upi", "upi_id": "lakshmi@okaxis"}, headers=auth_for(sitter))
    assert checklist(client, sitter, "sitter")[0]["profile"]["status"] == "to_do"
    upload_bytes(client, storage, sitter, "photo", JPEG)
    assert checklist(client, sitter, "sitter")[0]["profile"]["status"] == "waiting"


def test_parents_see_a_live_sitters_photo(client, storage, finished_parent, make_sitter):  # noqa: F811
    with_photo = make_sitter("With Photo")
    make_sitter("No Photo")
    upload_bytes(client, storage, with_photo, "photo", JPEG)

    photos = {
        item["full_name"]: item["photo_url"]
        for item in client.get("/parent/sitters", params={"plan": "pause"}, headers=auth_for(finished_parent)).json()
    }
    assert photos["No Photo"] is None
    assert photos["With Photo"].startswith(f"https://fake.storage/view/{with_photo['id']}/")
    detail = client.get(f"/parent/sitters/{with_photo['id']}", headers=auth_for(finished_parent)).json()
    assert detail["photo_url"].startswith("https://fake.storage/view/")
