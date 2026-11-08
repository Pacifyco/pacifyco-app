"""verification queue

The admin verification queue (CLAUDE.md 7, phase 3):
- `onboarding_steps`: an admin's review of a sitter's profile, ID documents and police certificate
  (steps 1-3). References and the psychology test keep their own outcomes. No row = not reviewed.
- `sitters.level` (pause|unwind|recharge), null until an admin sets it (CLAUDE.md 6.2).
- `children.verified_by`, `verified_at`, `verification_notes`: kept after the birth certificate is
  deleted on approval (CLAUDE.md 7: keep status, verifier and date).

Like every table: RLS on with no policies, nothing for the browser roles.

Revision ID: 55d0da5cd21c
Revises: 7c4e9a21f6b3
Create Date: 2026-11-08 19:45:35

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

BROWSER_ROLES = ["anon", "authenticated"]

# revision identifiers, used by Alembic.
revision: str = "55d0da5cd21c"
down_revision: str | Sequence[str] | None = "7c4e9a21f6b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(*values: str, name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def upgrade() -> None:
    op.create_table(
        "onboarding_steps",
        sa.Column("sitter_id", sa.Uuid(), nullable=False),
        sa.Column("step", _enum("profile", "identity_documents", "police_certificate", name="onboarding_step"), nullable=False),
        sa.Column("status", _enum("pending", "approved", "rejected", name="onboarding_step_status"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["profiles.id"], name=op.f("fk_onboarding_steps_reviewed_by_profiles"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["sitter_id"], ["sitters.profile_id"], name=op.f("fk_onboarding_steps_sitter_id_sitters"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("sitter_id", "step", name=op.f("pk_onboarding_steps")),
    )
    op.execute("ALTER TABLE onboarding_steps ENABLE ROW LEVEL SECURITY")
    for role in BROWSER_ROLES:
        op.execute(
            f"""
            DO $$ BEGIN
              IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                REVOKE ALL ON onboarding_steps FROM {role};
              END IF;
            END $$;
            """
        )

    op.add_column("children", sa.Column("verified_by", sa.Uuid(), nullable=True))
    op.add_column("children", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("children", sa.Column("verification_notes", sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f("fk_children_verified_by_profiles"), "children", "profiles", ["verified_by"], ["id"], ondelete="SET NULL"
    )
    op.add_column("sitters", sa.Column("level", _enum("pause", "unwind", "recharge", name="sitter_level"), nullable=True))


def downgrade() -> None:
    op.drop_column("sitters", "level")
    op.drop_constraint(op.f("fk_children_verified_by_profiles"), "children", type_="foreignkey")
    op.drop_column("children", "verification_notes")
    op.drop_column("children", "verified_at")
    op.drop_column("children", "verified_by")
    op.drop_table("onboarding_steps")
