"""When a sitter moved on from the References step (Reuben, 2026-11-16): the step is optional, but it shows
"Done" only once she has been on it and pressed Continue, whether or not she added one.

Sitters already past it (a reference given, payout details saved, or approved) count as having seen it.

Revision ID: e5b7d9f1a3c4
Revises: d4a6c8e0f2b1
Create Date: 2026-11-16 12:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "e5b7d9f1a3c4"
down_revision = "d4a6c8e0f2b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sitters", sa.Column("references_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        'UPDATE sitters SET references_confirmed_at = now() WHERE payout_method IS NOT NULL'
        " OR onboarding_status = 'approved'"
        ' OR EXISTS (SELECT 1 FROM "references" r WHERE r.sitter_id = sitters.profile_id)'
    )


def downgrade() -> None:
    op.drop_column("sitters", "references_confirmed_at")
