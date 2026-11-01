"""api database role

The API connects as its own role, `pacifyco_api`, not as the role that runs migrations (CLAUDE.md
section 5). It can read and write rows but can't create, change or drop tables:

- BYPASSRLS, because every table has RLS with no policies (so browser roles see nothing).
- SELECT, INSERT, UPDATE, DELETE on every table, now and in later migrations (default privileges).
- The audit log is append-only for the API: no UPDATE or DELETE.
- No access to alembic_version.

The role is created without a password (NOLOGIN). Each deployed database gets its password once, by
hand, as described in the README ("API database role"); that's a credential, not a schema change.

Roles belong to the whole Postgres server, not one database, so downgrade removes the grants but
leaves the role.

Revision ID: 45182d37e876
Revises: 2782b45c8775
Create Date: 2026-11-01 09:57:13.204011

"""

from collections.abc import Sequence

from alembic import op

API_ROLE = "pacifyco_api"
APPEND_ONLY_TABLES = ["audit_log"]

# revision identifiers, used by Alembic.
revision: str = "45182d37e876"
down_revision: str | Sequence[str] | None = "2782b45c8775"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        f"""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{API_ROLE}') THEN
            CREATE ROLE {API_ROLE} NOLOGIN BYPASSRLS;
          END IF;
        END $$;
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {API_ROLE}")
    op.execute(f"REVOKE CREATE ON SCHEMA public FROM {API_ROLE}")

    # Tables that exist now...
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {API_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {API_ROLE}")
    # ...and tables later migrations create (as the same migration role).
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {API_ROLE}"
    )
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {API_ROLE}")

    op.execute(f"REVOKE ALL ON alembic_version FROM {API_ROLE}")
    for table in APPEND_ONLY_TABLES:
        op.execute(f'REVOKE UPDATE, DELETE ON "{table}" FROM {API_ROLE}')


def downgrade() -> None:
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {API_ROLE}"
    )
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM {API_ROLE}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {API_ROLE}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {API_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {API_ROLE}")
