"""Name is asked for after sign-up, so profiles.full_name can be empty (CLAUDE.md 6.13)

Revision ID: 4b8e1f0c2a7d
Revises: 55d0da5cd21c
Create Date: 2026-11-08 22:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "4b8e1f0c2a7d"
down_revision = "55d0da5cd21c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("profiles", "full_name", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE profiles SET full_name = '' WHERE full_name IS NULL")
    op.alter_column("profiles", "full_name", existing_type=sa.Text(), nullable=False)
