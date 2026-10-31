"""Migrations: run cleanly on an empty database, reverse cleanly, match the models, and lock every
table down (RLS with no policies, no browser-role access). CLAUDE.md sections 2.7 and 5."""

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import DataError, DBAPIError, IntegrityError, ProgrammingError

import app.models  # noqa: F401
from app.db import Base

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
BROWSER_ROLES = ["anon", "authenticated"]
LAUNCH_PIN_CODES = {"560001", "560034", "560038", "560078", "560084", "560095", "560103"}
PROFILE_ID = "00000000-0000-0000-0000-000000000001"


def alembic_config(db_engine) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", db_engine.url.render_as_string(hide_password=False))
    config.attributes["configure_logger"] = False
    return config


def public_tables(conn) -> set[str]:
    rows = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
    return {row[0] for row in rows}


def simulate_supabase_roles(db_engine) -> None:
    """Create Supabase's browser roles and give them Supabase's default grants on new tables."""
    with db_engine.begin() as conn:
        for role in BROWSER_ROLES:
            conn.execute(
                text(
                    f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') "
                    f"THEN CREATE ROLE {role} NOLOGIN; END IF; END $$;"
                )
            )
            conn.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {role}"))


@pytest.fixture(scope="module")
def migrated(db_engine):
    config = alembic_config(db_engine)
    command.downgrade(config, "base")
    simulate_supabase_roles(db_engine)
    command.upgrade(config, "head")
    return config


@pytest.fixture
def conn(db_engine, migrated):
    """A connection whose changes are rolled back after each test."""
    with db_engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


def insert_profile(conn, role="sitter", profile_id=PROFILE_ID):
    conn.execute(
        text("INSERT INTO profiles (id, role, full_name, email) VALUES (:id, :role, 'Test', :email)"),
        {"id": profile_id, "role": role, "email": f"{profile_id}@example.com"},
    )


# ---------- runs cleanly and reverses ----------


def test_downgrade_to_empty_and_upgrade_again(db_engine, migrated):
    command.downgrade(migrated, "base")
    with db_engine.connect() as c:
        assert public_tables(c) == {"alembic_version"}
    simulate_supabase_roles(db_engine)
    command.upgrade(migrated, "head")
    with db_engine.connect() as c:
        assert public_tables(c) >= set(Base.metadata.tables)


def test_models_match_migrations(db_engine, migrated):
    with db_engine.connect() as c:
        diff = compare_metadata(MigrationContext.configure(c, opts={"compare_type": True}), Base.metadata)
    assert diff == [], f"Models and migrations differ; write a migration: {diff}"


# ---------- locked down ----------


def test_every_table_has_row_level_security(conn):
    rows = conn.execute(
        text(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r' AND NOT c.relrowsecurity"
        )
    )
    assert [row[0] for row in rows] == [], "Enable RLS on every new table (see lock_down_tables)"


def test_no_rls_policies_exist(conn):
    count = conn.execute(text("SELECT count(*) FROM pg_policies WHERE schemaname = 'public'")).scalar_one()
    assert count == 0


@pytest.mark.parametrize("role", BROWSER_ROLES)
def test_browser_roles_have_no_table_privileges(conn, role):
    granted = [
        table
        for table in public_tables(conn)
        if conn.execute(
            text("SELECT has_table_privilege(:role, :table, 'SELECT,INSERT,UPDATE,DELETE')"),
            {"role": role, "table": f'public."{table}"'},
        ).scalar_one()
    ]
    assert granted == []


@pytest.mark.parametrize("role", BROWSER_ROLES)
def test_browser_roles_cannot_read_profiles(conn, role):
    insert_profile(conn)
    conn.execute(text(f"SET LOCAL ROLE {role}"))
    with pytest.raises(DBAPIError, match="permission denied"):
        conn.execute(text("SELECT * FROM profiles"))


def test_rls_hides_rows_even_if_a_grant_slips_through(conn):
    insert_profile(conn)
    conn.execute(text("GRANT SELECT ON profiles TO anon"))
    conn.execute(text("SET LOCAL ROLE anon"))
    assert conn.execute(text("SELECT count(*) FROM profiles")).scalar_one() == 0


# ---------- seed data and constraints ----------


def test_launch_pin_codes_seeded_and_active(conn):
    rows = conn.execute(text("SELECT pin_code, active FROM service_area_pincodes")).all()
    assert {row.pin_code for row in rows} == LAUNCH_PIN_CODES
    assert all(row.active for row in rows)


def expect_rejected(conn, sql, params=None, errors=(IntegrityError, DataError)):
    with pytest.raises(errors):
        with conn.begin_nested():
            conn.execute(text(sql), params or {})


@pytest.mark.parametrize("rate", [7_999, 12_001])
def test_sitter_rate_outside_80_to_120_rupees_rejected(conn, rate):
    insert_profile(conn)
    expect_rejected(
        conn, "INSERT INTO sitters (profile_id, hourly_rate_paise) VALUES (:id, :rate)", {"id": PROFILE_ID, "rate": rate}
    )


@pytest.mark.parametrize("rate", [8_000, 12_000])
def test_sitter_rate_boundaries_accepted(conn, rate):
    insert_profile(conn)
    conn.execute(
        text("INSERT INTO sitters (profile_id, hourly_rate_paise) VALUES (:id, :rate)"), {"id": PROFILE_ID, "rate": rate}
    )


def test_unknown_role_rejected(conn):
    expect_rejected(conn, "INSERT INTO profiles (id, role, full_name, email) VALUES (gen_random_uuid(), 'nanny', 'X', 'x@x.in')")


def test_unknown_status_rejected(conn):
    insert_profile(conn)
    expect_rejected(conn, "UPDATE profiles SET status = 'banned' WHERE id = :id", {"id": PROFILE_ID})


@pytest.mark.parametrize("pin_code", ["56000", "5600011", "56000A"])
def test_bad_pin_code_rejected(conn, pin_code):
    insert_profile(conn)
    expect_rejected(conn, "UPDATE profiles SET pin_code = :pin WHERE id = :id", {"pin": pin_code, "id": PROFILE_ID})


def test_new_profile_defaults_to_pending(conn):
    insert_profile(conn)
    status = conn.execute(text("SELECT status FROM profiles WHERE id = :id"), {"id": PROFILE_ID}).scalar_one()
    assert status == "pending"


def test_child_requires_date_of_birth(conn):
    insert_profile(conn, role="parent")
    conn.execute(text("INSERT INTO parents (profile_id) VALUES (:id)"), {"id": PROFILE_ID})
    expect_rejected(conn, "INSERT INTO children (parent_id, name) VALUES (:id, 'Asha')", {"id": PROFILE_ID})


def test_audit_log_id_cannot_be_set_by_hand(conn):
    expect_rejected(
        conn, "INSERT INTO audit_log (id, action, entity, entity_id) VALUES (1, 'a', 'b', 'c')", errors=ProgrammingError
    )
