"""A removed reference is kept, marked removed, so a sitter can't give the same number again
(Reuben, 2026-11-13: "can't be the same as the user's number or any other number they previously
submitted").

Revision ID: c1f3a5b7d9e2
Revises: b8d2e4f6a1c3
Create Date: 2026-11-13 23:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "c1f3a5b7d9e2"
down_revision = "b8d2e4f6a1c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("references", sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.execute('DELETE FROM "references" WHERE removed_at IS NOT NULL')
    op.drop_column("references", "removed_at")
