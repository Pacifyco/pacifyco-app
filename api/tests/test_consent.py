"""Parental consent (CLAUDE.md 7 and 9): four required consents plus optional, withdrawable
marketing, all ticked separately, with the Family Terms and privacy policy on the same page; required
before any child-linked document."""

import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import cli
from app.errors import AppError
from app.models import ConsentKind
from app.services import consent
from tests.test_auth import client  # noqa: F401  (fixture)
from tests.test_roles import as_user, make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import ACCEPTED, PARENT, auth_for, user  # noqa: F401  (fixture)

CONSENT_FILE = Path(__file__).resolve().parents[2] / "web" / "src" / "content" / "consent.md"
FULL_STATUS = {
    "version": consent.CONSENT_VERSION,
    "required_accepted": False,
    "accepted_at": None,
    "marketing": False,
}


@pytest.fixture
def parent(client, db_engine, user):  # noqa: F811
    """A signed-up parent (profile and parents row). Removes consent rows first so cleanup can delete them."""
    assert client.post("/me/profile", json=PARENT, headers=auth_for(user)).status_code == 201
    yield user
    with db_engine.begin() as conn:  # as the owner: the API itself can't delete consent records
        conn.execute(text("DELETE FROM consents WHERE parent_id = :id"), {"id": user["id"]})


def accept(client, user):  # noqa: F811
    return client.post(
        "/parent/consent",
        json={"version": consent.CONSENT_VERSION, "marketing": False, "accepted": ACCEPTED},
        headers=auth_for(user),
    )


def consent_rows(db_engine, parent_id: uuid.UUID) -> list[dict]:
    with db_engine.connect() as conn:
        result = conn.execute(
            text("SELECT kind, version, accepted FROM consents WHERE parent_id = :id ORDER BY created_at"),
            {"id": parent_id},
        )
        return [dict(row) for row in result.mappings()]


def test_the_web_form_and_the_api_agree_on_the_version():
    match = re.search(r"^version:\s*(\S+)\s*$", CONSENT_FILE.read_text(encoding="utf-8"), re.MULTILINE)
    assert match, "web/src/content/consent.md needs a `version:` line in its front matter"
    assert match.group(1) == consent.CONSENT_VERSION


def test_new_parent_hasnt_consented(client, parent):  # noqa: F811
    response = client.get("/parent/consent", headers=auth_for(parent))
    assert response.status_code == 200
    assert response.json() == FULL_STATUS


def test_accepting_records_every_required_kind_and_the_marketing_choice(client, db_engine, parent):  # noqa: F811
    first = client.post(
        "/parent/consent",
        json={"version": consent.CONSENT_VERSION, "marketing": True, "accepted": ACCEPTED},
        headers=auth_for(parent),
    )
    assert first.status_code == 200
    body = first.json()
    assert body["required_accepted"] is True
    assert body["marketing"] is True
    assert body["accepted_at"] is not None

    rows = consent_rows(db_engine, parent["id"])
    assert {row["kind"] for row in rows} == {
        "own_data",
        "child_data",
        "share_care_details",
        "emergency_authorisation",
        "marketing",
    }
    assert all(row["accepted"] for row in rows)

    # Repeating keeps the first acceptance of each required kind, and doesn't add another marketing
    # row since the choice hasn't changed.
    again = client.post(
        "/parent/consent",
        json={"version": consent.CONSENT_VERSION, "marketing": True, "accepted": ACCEPTED},
        headers=auth_for(parent),
    )
    assert again.json()["accepted_at"] == body["accepted_at"]
    assert len(consent_rows(db_engine, parent["id"])) == 5


def test_marketing_can_be_withdrawn_and_reaccepted(client, db_engine, parent):  # noqa: F811
    signed_up = client.post(
        "/parent/consent",
        json={"version": consent.CONSENT_VERSION, "marketing": False, "accepted": ACCEPTED},
        headers=auth_for(parent),
    )
    assert signed_up.json()["marketing"] is False
    # Saying no at sign-up changes nothing: no marketing row at all yet.
    assert [r for r in consent_rows(db_engine, parent["id"]) if r["kind"] == "marketing"] == []

    withdraw = client.patch("/parent/consent/marketing", json={"accepted": False}, headers=auth_for(parent))
    assert withdraw.status_code == 200
    assert withdraw.json()["marketing"] is False
    # Still nothing to withdraw, so still no row.
    assert [r for r in consent_rows(db_engine, parent["id"]) if r["kind"] == "marketing"] == []

    opt_in = client.patch("/parent/consent/marketing", json={"accepted": True}, headers=auth_for(parent))
    assert opt_in.json()["marketing"] is True
    opt_out_again = client.patch("/parent/consent/marketing", json={"accepted": False}, headers=auth_for(parent))
    assert opt_out_again.json()["marketing"] is False

    marketing_rows = [r for r in consent_rows(db_engine, parent["id"]) if r["kind"] == "marketing"]
    assert [r["accepted"] for r in marketing_rows] == [True, False]  # append-only toggle history


@pytest.mark.parametrize("version", ["0.0-old", "", "9.9"])
def test_accepting_a_version_that_isnt_current_is_refused(client, db_engine, parent, version):  # noqa: F811
    response = client.post(
        "/parent/consent", json={"version": version, "marketing": False, "accepted": ACCEPTED}, headers=auth_for(parent)
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "consent_outdated"
    assert consent_rows(db_engine, parent["id"]) == []


@pytest.mark.parametrize("role", ["sitter", "admin"])
def test_only_parents_have_a_consent_form(client, make_profile, role):  # noqa: F811
    user_id = make_profile(role)
    assert client.get("/parent/consent", headers=as_user(user_id)).status_code == 403
    body = {"version": consent.CONSENT_VERSION, "marketing": False}
    assert client.post("/parent/consent", json=body, headers=as_user(user_id)).status_code == 403
    assert (
        client.patch("/parent/consent/marketing", json={"accepted": True}, headers=as_user(user_id)).status_code == 403
    )


def test_child_documents_need_every_required_consent(client, db_engine, parent):  # noqa: F811
    """The guard phase 3's child document upload calls (CLAUDE.md 9, "Consent")."""
    with Session(db_engine) as db:
        with pytest.raises(AppError) as refused:
            consent.require_current_consent(db, parent["id"])
        assert refused.value.code == "consent_required"

        # Only some of the four required kinds doesn't count.
        db.execute(
            text("INSERT INTO consents (parent_id, kind, version) VALUES (:id, 'own_data', :v)"),
            {"id": parent["id"], "v": consent.CONSENT_VERSION},
        )
        db.commit()
        with pytest.raises(AppError):
            consent.require_current_consent(db, parent["id"])

        # Consent to an older version doesn't count either.
        db.execute(
            text("INSERT INTO consents (parent_id, kind, version) VALUES (:id, 'child_data', 'older')"),
            {"id": parent["id"]},
        )
        db.commit()
        with pytest.raises(AppError):
            consent.require_current_consent(db, parent["id"])

    accept(client, parent)
    with Session(db_engine) as db:
        consent.require_current_consent(db, parent["id"])  # no error


def test_a_parent_with_consent_records_isnt_an_empty_account(client, db_engine, parent, capsys):  # noqa: F811
    accept(client, parent)
    url = db_engine.url.render_as_string(hide_password=False)
    assert cli.delete_empty_profile(parent["email"], True, url) == 1
    assert "has records" in capsys.readouterr().err


def test_a_parent_profile_without_its_parent_record_is_refused_cleanly(client, make_profile):  # noqa: F811
    """Only happens if the database was edited outside the app; it must not crash."""
    response = client.post(
        "/parent/consent",
        json={"version": consent.CONSENT_VERSION, "marketing": False, "accepted": ACCEPTED},
        headers=as_user(make_profile("parent")),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "account_incomplete"


def test_every_consent_kind_is_a_real_enum_member():
    assert {k.value for k in ConsentKind} == {
        "own_data",
        "child_data",
        "share_care_details",
        "emergency_authorisation",
        "marketing",
    }


# ---------- the terms and privacy policy, ticked on this page (decided 2026-11-12) ----------


def accepted_kinds(db_engine, parent_id) -> list[str]:
    with db_engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT d.kind FROM legal_acceptances a JOIN legal_documents d ON d.id = a.document_id "
                "WHERE a.profile_id = :id ORDER BY d.kind"
            ),
            {"id": parent_id},
        )
        return [r.kind for r in result]


def test_consent_without_the_terms_is_refused(client, db_engine, parent):  # noqa: F811
    response = client.post(
        "/parent/consent", json={"version": consent.CONSENT_VERSION, "marketing": True}, headers=auth_for(parent)
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "terms_required"
    assert consent_rows(db_engine, parent["id"]) == []  # all or nothing
    assert accepted_kinds(db_engine, parent["id"]) == []


def test_consent_records_the_family_terms_and_privacy_policy(client, db_engine, parent):  # noqa: F811
    assert accepted_kinds(db_engine, parent["id"]) == []  # nothing at sign-up any more
    assert accept(client, parent).status_code == 200
    assert accepted_kinds(db_engine, parent["id"]) == ["parent_terms", "privacy_policy"]
    me = client.get("/me", headers=auth_for(parent)).json()
    assert me["terms_to_accept"] == []


def test_an_old_terms_version_on_the_consent_page_is_refused(client, db_engine, parent):  # noqa: F811
    old = [{**item, "version": "0.0-old"} if item["kind"] == "parent_terms" else item for item in ACCEPTED]
    response = client.post(
        "/parent/consent",
        json={"version": consent.CONSENT_VERSION, "marketing": False, "accepted": old},
        headers=auth_for(parent),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "terms_outdated"
    assert consent_rows(db_engine, parent["id"]) == []
