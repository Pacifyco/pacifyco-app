"""check in check out

Phase 8 (CLAUDE.md 6.7): the check-in and check-out codes, locations and lockout columns. Codes are kept
encrypted (FIELD_ENCRYPTION_KEY), not hashed: unlike a password, the parent needs to see the same code
again on the same screen, so it must be reversible -- nothing is ever stored in plain text.

Revision ID: c9e2a4f6b8d1
Revises: b7d1f4a9e3c2
Create Date: 2026-11-20 15:00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9e2a4f6b8d1"
down_revision: Union[str, Sequence[str], None] = "b7d1f4a9e3c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("check_in_code_encrypted", sa.LargeBinary(), nullable=True))
    op.add_column("bookings", sa.Column("check_out_code_encrypted", sa.LargeBinary(), nullable=True))
    op.add_column(
        "bookings", sa.Column("code_attempts", sa.SmallInteger(), nullable=False, server_default="0")
    )
    op.add_column(
        "bookings", sa.Column("codes_locked", sa.Boolean(), nullable=False, server_default="false")
    )
    op.add_column("bookings", sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bookings", sa.Column("check_in_lat", sa.Float(), nullable=True))
    op.add_column("bookings", sa.Column("check_in_lng", sa.Float(), nullable=True))
    op.add_column("bookings", sa.Column("checked_out_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bookings", sa.Column("check_out_lat", sa.Float(), nullable=True))
    op.add_column("bookings", sa.Column("check_out_lng", sa.Float(), nullable=True))
    op.create_check_constraint("ck_bookings_code_attempts_in_range", "bookings", "code_attempts BETWEEN 0 AND 5")
    op.create_check_constraint(
        "ck_bookings_checked_out_needs_checked_in", "bookings", "checked_out_at IS NULL OR checked_in_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_bookings_checked_out_needs_checked_in"), "bookings", type_="check")
    op.drop_constraint(op.f("ck_bookings_code_attempts_in_range"), "bookings", type_="check")
    op.drop_column("bookings", "check_out_lng")
    op.drop_column("bookings", "check_out_lat")
    op.drop_column("bookings", "checked_out_at")
    op.drop_column("bookings", "check_in_lng")
    op.drop_column("bookings", "check_in_lat")
    op.drop_column("bookings", "checked_in_at")
    op.drop_column("bookings", "codes_locked")
    op.drop_column("bookings", "code_attempts")
    op.drop_column("bookings", "check_out_code_encrypted")
    op.drop_column("bookings", "check_in_code_encrypted")
