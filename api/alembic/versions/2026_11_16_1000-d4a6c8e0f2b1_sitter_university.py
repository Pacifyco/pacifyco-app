"""A sitter's university and semester (Reuben, 2026-11-16): asked in "About you", required, seen by
admins and parents. Nullable so sitters who signed up earlier keep their rows; the form asks them next
time they save.

Revision ID: d4a6c8e0f2b1
Revises: c1f3a5b7d9e2
Create Date: 2026-11-16 10:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "d4a6c8e0f2b1"
down_revision = "c1f3a5b7d9e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sitters", sa.Column("university", sa.Text(), nullable=True))
    op.add_column("sitters", sa.Column("semester", sa.SmallInteger(), nullable=True))
    op.create_check_constraint(op.f("ck_sitters_semester_range"), "sitters", "semester BETWEEN 1 AND 10")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_sitters_semester_range"), "sitters", type_="check")
    op.drop_column("sitters", "semester")
    op.drop_column("sitters", "university")
