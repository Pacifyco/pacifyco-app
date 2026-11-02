"""consent kinds

Replaces the single parental consent form with Family Terms 11.2's five separate consents (four
required, one optional and withdrawable: marketing) plus the single-parent declaration used later
on the masked-Aadhaar upload screen (CLAUDE.md section 7). The old `consents` table had one row per
(parent, form_version); the new one has one row per (parent, kind, version), so it's recreated
rather than altered -- there's no real data to preserve (staging only, nothing in production yet).

Like every table: RLS on with no policies, nothing for the browser roles, append-only for the API.

Revision ID: d2d559d33cf0
Revises: 996b4788ada8
Create Date: 2026-11-02 16:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

API_ROLE = "pacifyco_api"
BROWSER_ROLES = ["anon", "authenticated"]

CONSENT_KINDS = [
    "own_data",
    "child_data",
    "share_care_details",
    "emergency_authorisation",
    "marketing",
    "single_parent_declaration",
]

# revision identifiers, used by Alembic.
revision: str = "d2d559d33cf0"
down_revision: str | Sequence[str] | None = "996b4788ada8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(op.f("ix_consents_parent_id"), table_name="consents")
    op.drop_table("consents")

    op.create_table(
        "consents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(*CONSENT_KINDS, name="consent_kind", native_enum=False, create_constraint=True, length=32),
            nullable=False,
        ),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("accepted", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["parents.profile_id"], name=op.f("fk_consents_parent_id_parents"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consents")),
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
    op.execute(f'REVOKE UPDATE, DELETE ON "consents" FROM {API_ROLE}')
