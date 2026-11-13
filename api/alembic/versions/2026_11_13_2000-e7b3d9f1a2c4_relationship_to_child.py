"""A parent's relationship to their children, asked for in "Your details" (Reuben, 2026-11-13).

Revision ID: e7b3d9f1a2c4
Revises: c4e8b2a6d1f3
Create Date: 2026-11-13 20:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "e7b3d9f1a2c4"
down_revision = "c4e8b2a6d1f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Parents only (sitters leave it empty): Mother, Father or Legal guardian.
    op.add_column("profiles", sa.Column("relationship_to_child", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_profiles_relationship_to_child"),
        "profiles",
        "relationship_to_child IS NULL OR relationship_to_child IN ('Mother', 'Father', 'Legal guardian')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_profiles_relationship_to_child"), "profiles", type_="check")
    op.drop_column("profiles", "relationship_to_child")
