"""Terms click-wrap (CLAUDE.md 7 and 9): sign-up can't complete without acceptance; each acceptance stores
version, time, IP and user agent; parents see parent terms and sitters the Sitter Terms; a new version
must be accepted before the next action that matters."""

import re
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import get_key_source
from app.errors import AppError
from app.main import create_app
from app.models import Profile
from app.services import legal
from tests.test_auth import FakeKeys, client, make_settings  # noqa: F401  (client is a fixture)
from tests.test_migrations import alembic_config
from tests.test_roles import as_user, make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import ACCEPTED, PARENT, auth_for, row, user  # noqa: F401  (user is a fixture)

CONTENT = Path(__file__).resolve().parents[2] / "web" / "src" / "content"
SITTER_DOCS = ["privacy_policy", "sitter_terms"]
PARENT_DOCS = ["parent_terms", "privacy_policy"]


def accepted_kinds(db_engine, profile_id) -> list[str]:
    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT d.kind FROM legal_acceptances a JOIN legal_documents d ON d.id = a.document_id "
                "WHERE a.profile_id = :id ORDER BY d.kind, d.version"
            ),
            {"id": profile_id},
        )
        return [r.kind for r in rows]


@contextmanager
def published(db_engine, kind: str, version: str, effective: str = "now()"):
    """Publish a new version for one test (as a migration would), then remove it again."""
    with db_engine.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO legal_documents (kind, version, effective_at, content_path) "
                f"VALUES (:k, :v, {effective}, 'test')"
            ),
            {"k": kind, "v": version},
        )
    try:
        yield
    finally:
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM legal_acceptances WHERE document_id IN "
                    "(SELECT id FROM legal_documents WHERE kind = :k AND version = :v)"
                ),
                {"k": kind, "v": version},
            )
            conn.execute(
                text("DELETE FROM legal_documents WHERE kind = :k AND version = :v"), {"k": kind, "v": version}
            )


@pytest.fixture
def client_with_ip(db_engine):
    command.upgrade(alembic_config(db_engine), "head")
    app = create_app(make_settings(db_engine))
    app.dependency_overrides[get_key_source] = FakeKeys
    return TestClient(app, client=("203.0.113.9", 50000))


# ---------- sign-up ----------


@pytest.mark.parametrize("role", ["parent", "sitter"])
def test_sign_up_cant_complete_without_accepting(client, db_engine, user, role):  # noqa: F811
    response = client.post("/me/profile", json={**PARENT, "role": role, "accepted": []}, headers=auth_for(user))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "terms_required"
    assert row(db_engine, "SELECT 1 FROM profiles WHERE id = :id", user["id"]) is None


def test_sitters_must_accept_the_sitter_terms_not_the_parent_terms(client, db_engine, user):  # noqa: F811
    parent_only = [item for item in ACCEPTED if item["kind"] != "sitter_terms"]
    response = client.post(
        "/me/profile", json={**PARENT, "role": "sitter", "accepted": parent_only}, headers=auth_for(user)
    )
    assert response.status_code == 422
    assert row(db_engine, "SELECT 1 FROM profiles WHERE id = :id", user["id"]) is None


def test_an_old_version_at_sign_up_is_refused(client, db_engine, user):  # noqa: F811
    old = [{**item, "version": "0.0-old"} if item["kind"] == "parent_terms" else item for item in ACCEPTED]
    response = client.post("/me/profile", json={**PARENT, "accepted": old}, headers=auth_for(user))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "terms_outdated"
    assert row(db_engine, "SELECT 1 FROM profiles WHERE id = :id", user["id"]) is None


@pytest.mark.parametrize(("role", "kinds"), [("parent", PARENT_DOCS), ("sitter", SITTER_DOCS)])
def test_each_role_records_its_own_documents(client, db_engine, user, role, kinds):  # noqa: F811
    assert client.post("/me/profile", json={**PARENT, "role": role}, headers=auth_for(user)).status_code == 201
    assert accepted_kinds(db_engine, user["id"]) == kinds


def test_acceptance_stores_version_time_ip_and_user_agent(client_with_ip, db_engine, user):  # noqa: F811
    headers = {**auth_for(user), "User-Agent": "Mozilla/5.0 (Test) " + "x" * 600}
    assert client_with_ip.post("/me/profile", json={**PARENT, "role": "sitter"}, headers=headers).status_code == 201
    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT d.kind, d.version, a.method, a.accepted_at, host(a.ip_address) AS ip, a.user_agent "
                "FROM legal_acceptances a JOIN legal_documents d ON d.id = a.document_id "
                "WHERE a.profile_id = :id ORDER BY d.kind"
            ),
            {"id": user["id"]},
        ).mappings()
        rows = [dict(r) for r in rows]
    assert [(r["kind"], r["version"]) for r in rows] == [("privacy_policy", "0.1-draft"), ("sitter_terms", "1.1")]
    for r in rows:
        assert r["method"] == "clickwrap"
        assert r["accepted_at"] is not None
        assert r["ip"] == "203.0.113.9"
        assert r["user_agent"].startswith("Mozilla/5.0 (Test) ")
        assert len(r["user_agent"]) == legal.USER_AGENT_MAX


# ---------- re-acceptance ----------


@pytest.mark.parametrize(("role", "kinds"), [("parent", PARENT_DOCS), ("sitter", SITTER_DOCS), ("admin", [])])
def test_accounts_without_acceptances_are_asked(client, make_profile, role, kinds):  # noqa: F811
    me = client.get("/me", headers=as_user(make_profile(role))).json()
    assert sorted(item["kind"] for item in me["terms_to_accept"]) == kinds


def test_a_new_version_must_be_accepted_again(client, db_engine, user):  # noqa: F811
    assert client.post("/me/profile", json=PARENT, headers=auth_for(user)).status_code == 201
    with published(db_engine, "parent_terms", "0.2-test"):
        me = client.get("/me", headers=auth_for(user)).json()
        assert me["terms_to_accept"] == [{"kind": "parent_terms", "version": "0.2-test"}]
        with Session(db_engine) as db:
            with pytest.raises(AppError) as blocked:
                legal.require_current_terms(db, db.get(Profile, user["id"]))
            assert blocked.value.code == "terms_required"

        # Accepting the old version again doesn't help...
        old = client.post("/me/terms", json={"accepted": ACCEPTED}, headers=auth_for(user))
        assert old.status_code == 409
        # ...the new one does.
        new = [{**item, "version": "0.2-test"} if item["kind"] == "parent_terms" else item for item in ACCEPTED]
        response = client.post("/me/terms", json={"accepted": new}, headers=auth_for(user))
        assert response.status_code == 200
        assert response.json()["terms_to_accept"] == []
        with Session(db_engine) as db:
            legal.require_current_terms(db, db.get(Profile, user["id"]))  # no error
        # Both acceptances are kept.
        assert accepted_kinds(db_engine, user["id"]) == ["parent_terms", "parent_terms", "privacy_policy"]


def test_a_version_announced_for_later_isnt_required_yet(client, db_engine, user):  # noqa: F811
    """Changes affecting pay or rights take effect 14 days after they're announced."""
    assert client.post("/me/profile", json={**PARENT, "role": "sitter"}, headers=auth_for(user)).status_code == 201
    with published(db_engine, "sitter_terms", "1.2-test", effective="now() + interval '14 days'"):
        assert client.get("/me", headers=auth_for(user)).json()["terms_to_accept"] == []


def test_accepting_is_for_joined_unblocked_people(client, make_profile):  # noqa: F811
    blocked = client.post("/me/terms", json={"accepted": ACCEPTED}, headers=as_user(make_profile("parent", "removed")))
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "account_blocked"
    ok = client.post("/me/terms", json={"accepted": ACCEPTED}, headers=as_user(make_profile("sitter")))
    assert ok.status_code == 200
    assert ok.json()["terms_to_accept"] == []


# ---------- the web texts and the database agree ----------


def front_matter_version(path: Path) -> str:
    match = re.search(r"^version:\s*(\S+)\s*$", path.read_text(encoding="utf-8"), re.MULTILINE)
    assert match, f"{path.name} needs a `version:` line"
    return match.group(1)


def test_web_texts_match_the_current_versions(db_engine):
    command.upgrade(alembic_config(db_engine), "head")
    with Session(db_engine) as db:
        current = {kind.value: doc.version for kind, doc in legal.current_documents(db).items()}
    assert current["privacy_policy"] == front_matter_version(CONTENT / "privacy-policy.md")
    # Final terms are one file per version, named by it.
    assert (CONTENT / f"sitter-terms-v{current['sitter_terms']}.md").exists()
    assert (CONTENT / f"family-terms-v{current['parent_terms']}.md").exists()
