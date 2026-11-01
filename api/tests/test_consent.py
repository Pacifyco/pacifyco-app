"""Parental consent (CLAUDE.md 7 and 9): versioned, recorded once per version, required before child documents."""

import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import cli
from app.errors import AppError
from app.services import consent
from tests.test_auth import client  # noqa: F401  (fixture)
from tests.test_roles import as_user, make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, user  # noqa: F401  (fixture)

CONSENT_FILE = Path(__file__).resolve().parents[2] / "web" / "src" / "content" / "consent.md"


@pytest.fixture
def parent(client, db_engine, user):  # noqa: F811
    """A signed-up parent (profile and parents row). Removes consent rows first so cleanup can delete them."""
    assert client.post("/me/profile", json=PARENT, headers=auth_for(user)).status_code == 201
    yield user
    with db_engine.begin() as conn:  # as the owner: the API itself can't delete consent records
        conn.execute(text("DELETE FROM consents WHERE parent_id = :id"), {"id": user["id"]})


def consent_rows(db_engine, parent_id: uuid.UUID) -> list[dict]:
    with db_engine.connect() as conn:
        result = conn.execute(
            text("SELECT form_version, accepted_at FROM consents WHERE parent_id = :id"), {"id": parent_id}
        )
        return [dict(row) for row in result.mappings()]


def test_the_web_form_and_the_api_agree_on_the_version():
    match = re.search(r"^version:\s*(\S+)\s*$", CONSENT_FILE.read_text(encoding="utf-8"), re.MULTILINE)
    assert match, "web/src/content/consent.md needs a `version:` line in its front matter"
    assert match.group(1) == consent.CONSENT_VERSION


def test_new_parent_hasnt_consented(client, parent):  # noqa: F811
    response = client.get("/parent/consent", headers=auth_for(parent))
    assert response.status_code == 200
    assert response.json() == {"version": consent.CONSENT_VERSION, "accepted_at": None}


def test_accepting_records_version_and_time_once(client, db_engine, parent):  # noqa: F811
    first = client.post("/parent/consent", json={"version": consent.CONSENT_VERSION}, headers=auth_for(parent))
    assert first.status_code == 200
    assert first.json()["accepted_at"] is not None

    again = client.post("/parent/consent", json={"version": consent.CONSENT_VERSION}, headers=auth_for(parent))
    assert again.json()["accepted_at"] == first.json()["accepted_at"]  # the first acceptance is kept
    rows = consent_rows(db_engine, parent["id"])
    assert [row["form_version"] for row in rows] == [consent.CONSENT_VERSION]
    assert client.get("/parent/consent", headers=auth_for(parent)).json()["accepted_at"] == first.json()["accepted_at"]


@pytest.mark.parametrize("version", ["0.0-old", "", "9.9"])
def test_accepting_a_version_that_isnt_current_is_refused(client, db_engine, parent, version):  # noqa: F811
    response = client.post("/parent/consent", json={"version": version}, headers=auth_for(parent))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "consent_outdated"
    assert consent_rows(db_engine, parent["id"]) == []


@pytest.mark.parametrize("role", ["sitter", "admin"])
def test_only_parents_have_a_consent_form(client, make_profile, role):  # noqa: F811
    user_id = make_profile(role)
    assert client.get("/parent/consent", headers=as_user(user_id)).status_code == 403
    assert (
        client.post("/parent/consent", json={"version": consent.CONSENT_VERSION}, headers=as_user(user_id)).status_code
        == 403
    )


def test_child_documents_need_the_current_version(client, db_engine, parent):  # noqa: F811
    """The guard phase 3's child document upload calls (CLAUDE.md 9, "Consent")."""
    with Session(db_engine) as db:
        with pytest.raises(AppError) as refused:
            consent.require_current_consent(db, parent["id"])
        assert refused.value.code == "consent_required"

        # Consent to an older version doesn't count.
        db.execute(text("INSERT INTO consents (parent_id, form_version) VALUES (:id, 'older')"), {"id": parent["id"]})
        db.commit()
        with pytest.raises(AppError):
            consent.require_current_consent(db, parent["id"])

    client.post("/parent/consent", json={"version": consent.CONSENT_VERSION}, headers=auth_for(parent))
    with Session(db_engine) as db:
        consent.require_current_consent(db, parent["id"])  # no error


def test_a_parent_with_consent_records_isnt_an_empty_account(client, db_engine, parent, capsys):  # noqa: F811
    client.post("/parent/consent", json={"version": consent.CONSENT_VERSION}, headers=auth_for(parent))
    url = db_engine.url.render_as_string(hide_password=False)
    assert cli.delete_empty_profile(parent["email"], True, url) == 1
    assert "has records" in capsys.readouterr().err
