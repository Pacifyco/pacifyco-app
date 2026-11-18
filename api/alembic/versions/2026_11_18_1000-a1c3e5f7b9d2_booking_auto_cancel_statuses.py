"""booking auto-cancel statuses

Phase 6, "Frequent job": two booking statuses for Pacifyco's own cancellations of `pending_payment`
bookings (CLAUDE.md 6.1 and 6.4): `cancelled_unpaid` (no payment sent by the deadline, 3 hours before
the start) and `cancelled_slot_taken` (another booking for an overlapping time with her was confirmed
first).

Revision ID: a1c3e5f7b9d2
Revises: f9ef16dd91b3
Create Date: 2026-11-18 10:00:00

"""

from typing import Sequence, Union

from alembic import op

revision: str = "a1c3e5f7b9d2"
down_revision: Union[str, Sequence[str], None] = "f9ef16dd91b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BEFORE = [
    "pending_payment",
    "confirmed",
    "in_progress",
    "completed",
    "cancelled_parent",
    "cancelled_parent_late",
    "cancelled_sitter",
    "cancelled_sitter_late",
    "parent_absent",
    "sitter_no_show",
]
AFTER = [*BEFORE, "cancelled_unpaid", "cancelled_slot_taken"]


def _quoted(values: list[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _allow(values: list[str]) -> None:
    op.drop_constraint(op.f("ck_bookings_booking_status"), "bookings", type_="check")
    op.create_check_constraint(op.f("ck_bookings_booking_status"), "bookings", f"status IN ({_quoted(values)})")


def upgrade() -> None:
    _allow(AFTER)


def downgrade() -> None:
    # No older status says "cancelled by Pacifyco", and relabelling a money record would misstate it, so
    # this refuses while any booking has one of these statuses.
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT FROM bookings WHERE status IN ('cancelled_unpaid', 'cancelled_slot_taken')) THEN
            RAISE EXCEPTION 'Bookings were cancelled by Pacifyco; they have no earlier status to go back to';
          END IF;
        END $$;
        """
    )
    _allow(BEFORE)
