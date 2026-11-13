"""`python -m app.cli reset-staging-accounts` (Reuben, 2026-11-13): removes every parent and sitter on a
staging database, with their records, files and sign-in accounts. Admins stay; production is refused."""

from sqlalchemy import text

from app import cli
from tests.test_documents import (  # noqa: F401  (fixtures)
    admin,
    client,
    parent,
    request_upload,
    scalar,
    sitter,
    storage,
)
from tests.test_roles import as_user, make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import auth_for, user  # noqa: F401  (fixture)
from tests.test_verification import add_references, family_with_certificate, review


def count(db_engine, sql: str, **params) -> int:
    with db_engine.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


def url_of(db_engine) -> str:
    return db_engine.url.render_as_string(hide_password=False)


def test_without_yes_it_only_counts(client, db_engine, storage, parent, sitter, monkeypatch, capsys):  # noqa: F811
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    family_with_certificate(client, db_engine, storage, parent)
    assert cli.reset_staging_accounts(False, url_of(db_engine), None, None) == 0
    assert "Would remove 1 parents (1 children) and 1 sitters, 1 documents" in capsys.readouterr().out
    assert count(db_engine, "SELECT count(*) FROM profiles WHERE id = :id", id=parent["id"]) == 1


def test_it_removes_every_parent_and_sitter_but_keeps_admins(
    client,  # noqa: F811
    db_engine,
    storage,  # noqa: F811
    parent,  # noqa: F811
    sitter,  # noqa: F811
    admin,  # noqa: F811
    monkeypatch,
):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    child_id, document_id = family_with_certificate(client, db_engine, storage, parent)
    review(client, admin, f"/admin/children/{child_id}/decision", approved=False, reason="Blurry")  # audit rows
    add_references(client, sitter)
    files, sign_ins = [], []

    assert cli.reset_staging_accounts(True, url_of(db_engine), files.append, sign_ins.append) == 0

    ids = [parent["id"], sitter["id"]]
    for table, column in (
        ("profiles", "id"),
        ("consents", "parent_id"),
        ("legal_acceptances", "profile_id"),
        ("documents", "owner_profile_id"),
        ("references", "sitter_id"),
        ("audit_log", "actor_id"),
    ):
        assert count(db_engine, f'SELECT count(*) FROM "{table}" WHERE {column} = ANY(:ids)', ids=ids) == 0, table
    assert count(db_engine, "SELECT count(*) FROM children WHERE id = :id", id=child_id) == 0
    assert count(db_engine, "SELECT count(*) FROM audit_log WHERE entity_id = :id", id=str(child_id)) == 0
    assert count(db_engine, "SELECT count(*) FROM profiles WHERE id = :id", id=admin) == 1  # admins stay
    assert files == [f"{parent['id']}/{document_id}"]
    assert sorted(sign_ins) == sorted(ids)


def test_production_is_refused(db_engine, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert cli.reset_staging_accounts(True, url_of(db_engine), None, None) == 1


def test_without_the_supabase_keys_nothing_is_deleted(db_engine, parent, monkeypatch):  # noqa: F811
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    assert cli.reset_staging_accounts(True, url_of(db_engine)) == 1
    assert count(db_engine, "SELECT count(*) FROM profiles WHERE id = :id", id=parent["id"]) == 1
