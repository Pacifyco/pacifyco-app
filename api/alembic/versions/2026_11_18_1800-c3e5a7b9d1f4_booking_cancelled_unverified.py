"""booking cancelled unverified

The `cancelled_unverified` booking status (CLAUDE.md 6.4; Reuben, 2026-11-18): a paid booking whose start
came while a child on it still wasn't verified. It's cancelled and the parent refunded in full. (Paid
bookings waiting for a child's verification no longer hold the sitter's time; that's code, not schema.)

Revision ID: c3e5a7b9d1f4
Revises: b2d4f6a8c0e1
Create Date: 2026-11-18 18:00:00

"""

from typing import Sequence, Union

from alembic import op

revision: str = "c3e5a7b9d1f4"
down_revision: Union[str, Sequence[str], None] = "b2d4f6a8c0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BEFORE = [
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
]
AFTER = [*BEFORE, "cancelled_unverified"]


def _quoted(values: list[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _allow(values: list[str]) -> None:
    op.drop_constraint(op.f("ck_bookings_booking_status"), "bookings", type_="check")
    op.create_check_constraint(op.f("ck_bookings_booking_status"), "bookings", f"status IN ({_quoted(values)})")


def upgrade() -> None:
    _allow(AFTER)


def downgrade() -> None:
    # No older status says this, and relabelling a refunded booking would misstate it, so this refuses
    # while any booking has it.
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT FROM bookings WHERE status = 'cancelled_unverified') THEN
            RAISE EXCEPTION 'Bookings were cancelled for unverified children; they have no earlier status to go back to';
          END IF;
        END $$;
        """
    )
    _allow(BEFORE)
