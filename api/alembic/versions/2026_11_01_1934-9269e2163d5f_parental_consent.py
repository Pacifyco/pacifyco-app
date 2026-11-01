"""parental consent

Records which version of the parental consent form each parent accepted, and when (CLAUDE.md 7).
Like every table: RLS on with no policies, nothing for the browser roles. Append-only for the API
(no UPDATE or DELETE), and a parent can't be deleted while they have consent records (RESTRICT).

Revision ID: 9269e2163d5f
Revises: 45182d37e876
Create Date: 2026-11-01 19:34:05.733779

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

API_ROLE = "pacifyco_api"
BROWSER_ROLES = ["anon", "authenticated"]

# revision identifiers, used by Alembic.
revision: str = "9269e2163d5f"
down_revision: str | Sequence[str] | None = "45182d37e876"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "consents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=False),
        sa.Column("form_version", sa.Text(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["parents.profile_id"], name=op.f("fk_consents_parent_id_parents"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consents")),
        sa.UniqueConstraint("parent_id", "form_version", name=op.f("uq_consents_parent_id")),
    )
    op.create_index(op.f("ix_consents_parent_id"), "consents", ["parent_id"], unique=False)

    op.execute('ALTER TABLE "consents" ENABLE ROW LEVEL SECURITY')
    for role in BROWSER_ROLES:
        op.execute(
            f"""
            DO $$ BEGIN
              IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                REVOKE ALL ON "consents" FROM {role};
              END IF;
            END $$;
            """
        )
    # The API role gets SELECT/INSERT/UPDATE/DELETE automatically (default privileges); take back the
    # last two so consent records can only be added.
    op.execute(f'REVOKE UPDATE, DELETE ON "consents" FROM {API_ROLE}')


def downgrade() -> None:
    op.drop_index(op.f("ix_consents_parent_id"), table_name="consents")
    op.drop_table("consents")
