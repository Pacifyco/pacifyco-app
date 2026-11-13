"""When a sitter last saved her health disclosure, even empty, so "Health disclosure" can be its own
onboarding step (Reuben, 2026-11-13). Sitters who already saved one count as done.

Revision ID: f9a1c3e5b7d2
Revises: e7b3d9f1a2c4
Create Date: 2026-11-13 21:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "f9a1c3e5b7d2"
down_revision = "e7b3d9f1a2c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sitters", sa.Column("health_disclosure_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE sitters SET health_disclosure_confirmed_at = now() WHERE health_disclosure_encrypted IS NOT NULL")


def downgrade() -> None:
    op.drop_column("sitters", "health_disclosure_confirmed_at")
