"""admin close

Phase 8 (CLAUDE.md 6.7): an admin can close a booking by hand -- an overdue check-out (still `in_progress`
30+ minutes past its end), or one whose codes got locked with no other way through. Adds the booking
status `closed_by_admin` and the columns that record who closed it and why.

Revision ID: d3f5b7a9c1e4
Revises: c9e2a4f6b8d1
Create Date: 2026-11-20 17:00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d3f5b7a9c1e4"
down_revision: Union[str, Sequence[str], None] = "c9e2a4f6b8d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUSES_BEFORE = [
    "requested",
    "request_declined",
    "request_lapsed",
    "pending_payment",
    "awaiting_verification",
    "confirmed",
    "in_progress",
    "completed",
    "cancelled_parent",
    "cancelled_parent_late",
    "cancelled_sitter",
    "cancelled_sitter_late",
    "parent_absent",
    "sitter_no_show",
    "cancelled_unpaid",
    "cancelled_slot_taken",
    "cancelled_unverified",
    "declined_man_at_home",
    "child_under_age",
    "sitter_left_unsafe",
]
STATUSES_AFTER = [*STATUSES_BEFORE, "closed_by_admin"]


def _quoted(values: list[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _allow_statuses(values: list[str]) -> None:
    op.drop_constraint(op.f("ck_bookings_booking_status"), "bookings", type_="check")
    op.create_check_constraint(op.f("ck_bookings_booking_status"), "bookings", f"status IN ({_quoted(values)})")


def upgrade() -> None:
    op.add_column("bookings", sa.Column("closed_by_admin_id", sa.Uuid(), nullable=True))
    op.add_column("bookings", sa.Column("close_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f("fk_bookings_closed_by_admin_id_profiles"),
        "bookings",
        "profiles",
        ["closed_by_admin_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_bookings_closed_has_reason"), "bookings", "(closed_by_admin_id IS NULL) = (close_reason IS NULL)"
    )
    _allow_statuses(STATUSES_AFTER)


def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT FROM bookings WHERE status = 'closed_by_admin') THEN
            RAISE EXCEPTION 'Bookings were closed by an admin; they have nowhere to go back to';
          END IF;
        END $$;
        """
    )
    _allow_statuses(STATUSES_BEFORE)
    op.drop_constraint(op.f("ck_bookings_closed_has_reason"), "bookings", type_="check")
    op.drop_constraint(op.f("fk_bookings_closed_by_admin_id_profiles"), "bookings", type_="foreignkey")
    op.drop_column("bookings", "close_reason")
    op.drop_column("bookings", "closed_by_admin_id")
