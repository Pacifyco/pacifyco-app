"""sitter references

Two references per sitter (CLAUDE.md section 7 step 4): name, phone, relationship, with an admin
recording the outcome later (phase 3's admin verification queue) -- `pending` until then. "references"
is a reserved SQL word, quoted like every other identifier Alembic emits.

Like every table: RLS on with no policies, nothing for the browser roles. Not append-only: a sitter
can remove and re-add a reference before it's reviewed.

Revision ID: a3f8c1d9e204
Revises: 724a55060e63
Create Date: 2026-11-02 22:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

BROWSER_ROLES = ["anon", "authenticated"]
OUTCOMES = ["pending", "approved", "rejected"]

# revision identifiers, used by Alembic.
revision: str = "a3f8c1d9e204"
down_revision: str | Sequence[str] | None = "724a55060e63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "references",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("sitter_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("relationship", sa.Text(), nullable=False),
        sa.Column(
            "outcome",
            sa.Enum(*OUTCOMES, name="reference_outcome", native_enum=False, create_constraint=True, length=32),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["sitter_id"], ["sitters.profile_id"], name=op.f("fk_references_sitter_id_sitters"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_references")),
    )
    op.create_index(op.f("ix_references_sitter_id"), "references", ["sitter_id"], unique=False)

    op.execute('ALTER TABLE "references" ENABLE ROW LEVEL SECURITY')
    for role in BROWSER_ROLES:
        op.execute(
            f"""
            DO $$ BEGIN
              IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                REVOKE ALL ON "references" FROM {role};
              END IF;
            END $$;
            """
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_references_sitter_id"), table_name="references")
    op.drop_table("references")
