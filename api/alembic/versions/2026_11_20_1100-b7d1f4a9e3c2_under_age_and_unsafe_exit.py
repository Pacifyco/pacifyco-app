"""under age and unsafe exit

Phase 7 (CLAUDE.md 6.5): two more reports during a booking. `child_under_age` (a child on the booking
turns out to be under 18 months, which should never happen) and `sitter_unsafe` (she needs to leave for
her own safety, once the child is with a parent). The booking statuses they close with: `child_under_age`
and `sitter_left_unsafe`.

Revision ID: b7d1f4a9e3c2
Revises: a8c0e2f4b6d7
Create Date: 2026-11-20 11:00:00

"""

from typing import Sequence, Union

from alembic import op

revision: str = "b7d1f4a9e3c2"
down_revision: Union[str, Sequence[str], None] = "a8c0e2f4b6d7"
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
]
STATUSES_AFTER = [*STATUSES_BEFORE, "child_under_age", "sitter_left_unsafe"]
KINDS_BEFORE = ["parent_absent", "sitter_no_show", "only_man_home"]
KINDS_AFTER = [*KINDS_BEFORE, "child_under_age", "sitter_unsafe"]


def _quoted(values: list[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _allow(table: str, constraint: str, column: str, values: list[str]) -> None:
    op.drop_constraint(op.f(constraint), table, type_="check")
    op.create_check_constraint(op.f(constraint), table, f"{column} IN ({_quoted(values)})")


def upgrade() -> None:
    _allow("bookings", "ck_bookings_booking_status", "status", STATUSES_AFTER)
    _allow("booking_reports", "ck_booking_reports_report_kind", "kind", KINDS_AFTER)


def downgrade() -> None:
    # Closed bookings and their reports have no earlier status or kind to go back to, so this refuses.
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT FROM bookings WHERE status IN ('child_under_age', 'sitter_left_unsafe'))
             OR EXISTS (SELECT FROM booking_reports WHERE kind IN ('child_under_age', 'sitter_unsafe')) THEN
            RAISE EXCEPTION 'Bookings were closed for an under-age child or an unsafe exit; they have nowhere to go back to';
          END IF;
        END $$;
        """
    )
    _allow("booking_reports", "ck_booking_reports_report_kind", "kind", KINDS_BEFORE)
    _allow("bookings", "ck_bookings_booking_status", "status", STATUSES_BEFORE)
