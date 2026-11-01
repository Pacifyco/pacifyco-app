"""Sign-up: choosing parent or sitter creates the profile once; admins only come from the CLI (CLAUDE.md 6.13)."""

import uuid

import pytest
from sqlalchemy import text

from app import cli
from app.services.accounts import normalise_mobile
from tests.test_auth import bearer, client, token  # noqa: F401  (client is a fixture)

# Ticked at sign-up. Covers both roles (each role's required documents are checked; others are ignored).
ACCEPTED = [
    {"kind": "parent_terms", "version": "0.1-draft"},
    {"kind": "sitter_terms", "version": "1.1"},
    {"kind": "privacy_policy", "version": "0.1-draft"},
]
PARENT = {
    "role": "parent",
    "full_name": "  Meera   Rao ",
    "phone": "+91 98765-43210",
    "pin_code": "560034",
    "accepted": ACCEPTED,
}


@pytest.fixture
def user(db_engine):
    """A fresh sign-in identity; its profile (if any) is removed afterwards."""
    user_id = uuid.uuid4()
    yield {"id": user_id, "email": f"{user_id}@example.com"}
    with db_engine.begin() as conn:  # as the owner: these records are append-only for the API
        for table in ("legal_acceptances", "consents"):
            column = "parent_id" if table == "consents" else "profile_id"
            conn.execute(text(f"DELETE FROM {table} WHERE {column} = :id"), {"id": user_id})
        conn.execute(text("DELETE FROM profiles WHERE id = :id"), {"id": user_id})


def auth_for(user, **claims) -> dict[str, str]:
    return bearer(token(**{"sub": str(user["id"]), "email": user["email"], **claims}))


def row(db_engine, sql: str, user_id):
    with db_engine.connect() as conn:
        return conn.execute(text(sql), {"id": user_id}).mappings().first()


def test_parent_sign_up_creates_profile_and_parent(client, db_engine, user):  # noqa: F811
    response = client.post("/me/profile", json=PARENT, headers=auth_for(user))
    assert response.status_code == 201
    assert response.json() == {
        "email": user["email"],
        "profile": {"role": "parent", "status": "pending", "full_name": "Meera Rao"},
        "terms_to_accept": [],  # accepted at sign-up
    }
    profile = row(db_engine, "SELECT role, phone, email, status, pin_code FROM profiles WHERE id = :id", user["id"])
    assert dict(profile) == {
        "role": "parent",
        "phone": "+919876543210",
        "email": user["email"],
        "status": "pending",
        "pin_code": "560034",
    }
    assert row(db_engine, "SELECT 1 FROM parents WHERE profile_id = :id", user["id"]) is not None
    assert row(db_engine, "SELECT 1 FROM sitters WHERE profile_id = :id", user["id"]) is None
    assert client.get("/me", headers=auth_for(user)).json()["profile"]["role"] == "parent"


def test_sitter_sign_up_creates_sitter_in_onboarding(client, db_engine, user):  # noqa: F811
    response = client.post("/me/profile", json={**PARENT, "role": "sitter"}, headers=auth_for(user))
    assert response.status_code == 201
    sitter = row(db_engine, "SELECT onboarding_status FROM sitters WHERE profile_id = :id", user["id"])
    assert sitter["onboarding_status"] == "in_progress"
    assert row(db_engine, "SELECT 1 FROM parents WHERE profile_id = :id", user["id"]) is None


def test_admin_cant_be_chosen_at_sign_up(client, db_engine, user):  # noqa: F811
    response = client.post("/me/profile", json={**PARENT, "role": "admin"}, headers=auth_for(user))
    assert response.status_code == 422
    assert row(db_engine, "SELECT 1 FROM profiles WHERE id = :id", user["id"]) is None


def test_role_cant_be_changed_by_signing_up_again(client, db_engine, user):  # noqa: F811
    assert client.post("/me/profile", json=PARENT, headers=auth_for(user)).status_code == 201
    again = client.post("/me/profile", json={**PARENT, "role": "sitter"}, headers=auth_for(user))
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "already_signed_up"
    assert row(db_engine, "SELECT role FROM profiles WHERE id = :id", user["id"])["role"] == "parent"
    assert row(db_engine, "SELECT 1 FROM sitters WHERE profile_id = :id", user["id"]) is None


def test_email_already_used_by_another_account(client, db_engine, user):  # noqa: F811
    other = uuid.uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO profiles (id, role, full_name, email) VALUES (:id, 'sitter', 'X', :email)"),
            {"id": other, "email": user["email"]},
        )
    try:
        response = client.post("/me/profile", json=PARENT, headers=auth_for(user))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "email_in_use"
    finally:
        with db_engine.begin() as conn:
            conn.execute(text("DELETE FROM profiles WHERE id = :id"), {"id": other})


@pytest.mark.parametrize(
    "change",
    [
        {"full_name": "   "},
        {"full_name": "x" * 101},
        {"full_name": "Meera\x00Rao"},
        {"phone": "12345"},
        {"phone": "5876543210"},  # Indian mobiles start 6–9
        {"phone": "+1 415 555 0100"},
        {"role": "nanny"},
        {"pin_code": "56003"},
        {"pin_code": "56003A"},
        {"pin_code": None},
    ],
)
def test_invalid_details_are_422_and_create_nothing(client, db_engine, user, change):  # noqa: F811
    response = client.post("/me/profile", json={**PARENT, **change}, headers=auth_for(user))
    assert response.status_code == 422
    assert "98765" not in response.text  # submitted values aren't echoed
    assert row(db_engine, "SELECT 1 FROM profiles WHERE id = :id", user["id"]) is None


def test_sign_up_needs_sign_in(client):  # noqa: F811
    assert client.post("/me/profile", json=PARENT).status_code == 401


def test_sign_up_needs_an_email_on_the_account(client, db_engine, user):  # noqa: F811
    response = client.post("/me/profile", json=PARENT, headers=auth_for(user, email=None))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "email_required"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("9876543210", "+919876543210"),
        ("+91 98765 43210", "+919876543210"),
        ("91-98765-43210", "+919876543210"),
        ("098765 43210", "+919876543210"),
        ("(+91) 6123456789", "+916123456789"),
        ("987654321", None),
        ("98765432100", None),
        ("080 234 5678", None),  # a Bengaluru landline
        ("", None),
    ],
)
def test_normalise_mobile(raw, expected):
    assert normalise_mobile(raw) == expected


# ---------- create-admin CLI ----------


@pytest.fixture
def database_url(db_engine):
    from alembic import command

    from tests.test_migrations import alembic_config

    command.upgrade(alembic_config(db_engine), "head")
    return db_engine.url.render_as_string(hide_password=False)


@pytest.fixture
def supabase_auth_users(db_engine):
    """A stand-in for Supabase's auth.users table, for the email lookup."""
    with db_engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA auth"))
        conn.execute(text("CREATE TABLE auth.users (id uuid PRIMARY KEY, email text)"))
    yield
    with db_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA auth CASCADE"))


def test_cli_creates_an_active_admin_from_the_sign_in_account(
    db_engine, database_url, supabase_auth_users, user, capsys
):
    with db_engine.begin() as conn:
        conn.execute(text("INSERT INTO auth.users VALUES (:id, :email)"), {"id": user["id"], "email": user["email"]})
    assert cli.create_admin(user["email"].upper(), "Reuben J", None, database_url) == 0
    profile = row(db_engine, "SELECT role, status, full_name FROM profiles WHERE id = :id", user["id"])
    assert dict(profile) == {"role": "admin", "status": "active", "full_name": "Reuben J"}
    assert "is now an admin" in capsys.readouterr().out


def test_cli_refuses_someone_who_hasnt_signed_in(database_url, supabase_auth_users, capsys):
    assert cli.create_admin("nobody@example.com", "N", None, database_url) == 1
    assert "sign in once first" in capsys.readouterr().err


def test_cli_wont_turn_a_parent_into_an_admin(client, db_engine, database_url, user, capsys):  # noqa: F811
    assert client.post("/me/profile", json=PARENT, headers=auth_for(user)).status_code == 201
    assert cli.create_admin(user["email"], "X", user["id"], database_url) == 1
    assert row(db_engine, "SELECT role FROM profiles WHERE id = :id", user["id"])["role"] == "parent"
    assert "already has a Pacify profile" in capsys.readouterr().err


def test_cli_with_user_id_works_without_supabase(db_engine, database_url, user, capsys):
    assert cli.create_admin(user["email"], "Local Admin", user["id"], database_url) == 0
    assert row(db_engine, "SELECT role FROM profiles WHERE id = :id", user["id"])["role"] == "admin"


def test_cli_without_supabase_asks_for_user_id(database_url, capsys):
    assert cli.create_admin("someone@example.com", "N", None, database_url) == 1
    assert "Pass --user-id" in capsys.readouterr().err


# ---------- delete-empty-profile CLI ----------


def profile_exists(db_engine, user_id) -> bool:
    return row(db_engine, "SELECT 1 FROM profiles WHERE id = :id", user_id) is not None


@pytest.mark.parametrize("role", ["parent", "sitter"])
def test_cli_deletes_an_empty_profile_only_with_yes(client, db_engine, database_url, user, role, capsys):  # noqa: F811
    assert client.post("/me/profile", json={**PARENT, "role": role}, headers=auth_for(user)).status_code == 201

    assert cli.delete_empty_profile(user["email"].upper(), False, database_url) == 0
    assert "Run again with --yes" in capsys.readouterr().out
    assert profile_exists(db_engine, user["id"])

    assert cli.delete_empty_profile(user["email"], True, database_url) == 0
    assert not profile_exists(db_engine, user["id"])
    for table in ("parents", "sitters"):
        assert row(db_engine, f"SELECT 1 FROM {table} WHERE profile_id = :id", user["id"]) is None
    # The email is free again: signing up works.
    assert client.post("/me/profile", json=PARENT, headers=auth_for(user)).status_code == 201


def test_cli_keeps_a_parent_with_children(client, db_engine, database_url, user, capsys):  # noqa: F811
    assert client.post("/me/profile", json=PARENT, headers=auth_for(user)).status_code == 201
    with db_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO children (parent_id, name, date_of_birth) VALUES (:id, 'Kid', '2022-01-01')"),
            {"id": user["id"]},
        )
    assert cli.delete_empty_profile(user["email"], True, database_url) == 1
    assert "has records" in capsys.readouterr().err
    assert profile_exists(db_engine, user["id"])


def test_cli_keeps_a_sitter_with_application_details(client, db_engine, database_url, user, capsys):  # noqa: F811
    assert client.post("/me/profile", json={**PARENT, "role": "sitter"}, headers=auth_for(user)).status_code == 201
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE sitters SET bio = 'Hello' WHERE profile_id = :id"), {"id": user["id"]})
    assert cli.delete_empty_profile(user["email"], True, database_url) == 1
    assert profile_exists(db_engine, user["id"])


def test_cli_keeps_someone_with_audit_history(client, db_engine, database_url, user, capsys):  # noqa: F811
    assert client.post("/me/profile", json=PARENT, headers=auth_for(user)).status_code == 201
    with db_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO audit_log (actor_id, action, entity, entity_id) VALUES (:id, 'x', 'y', 'z')"),
            {"id": user["id"]},
        )
    try:
        assert cli.delete_empty_profile(user["email"], True, database_url) == 1
        assert profile_exists(db_engine, user["id"])
    finally:
        with db_engine.begin() as conn:  # test cleanup as the owner (audit_log is append-only for the API)
            conn.execute(text("DELETE FROM audit_log WHERE actor_id = :id"), {"id": user["id"]})


def test_cli_delete_unknown_email(database_url, capsys):
    assert cli.delete_empty_profile("nobody@example.com", True, database_url) == 1
    assert "No Pacify profile" in capsys.readouterr().err
