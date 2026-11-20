"""only man home

Phase 7 (CLAUDE.md 6.5; decided 2026-11-12): the sitter may decline on arrival when the only adult at home is
a man. A third report kind, `only_man_home`, and the booking status it closes with, `declined_man_at_home`.

Revision ID: a8c0e2f4b6d7
Revises: 1ae5f9ea87ab
Create Date: 2026-11-20 09:00:00

"""

from typing import Sequence, Union

from alembic import op

revision: str = "a8c0e2f4b6d7"
down_revision: Union[str, Sequence[str], None] = "1ae5f9ea87ab"
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
]
STATUSES_AFTER = [*STATUSES_BEFORE, "declined_man_at_home"]
KINDS_BEFORE = ["parent_absent", "sitter_no_show"]
KINDS_AFTER = [*KINDS_BEFORE, "only_man_home"]


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
          IF EXISTS (SELECT FROM bookings WHERE status = 'declined_man_at_home')
             OR EXISTS (SELECT FROM booking_reports WHERE kind = 'only_man_home') THEN
            RAISE EXCEPTION 'Bookings were declined because only a man was at home; they have nowhere to go back to';
          END IF;
        END $$;
        """
    )
    _allow("booking_reports", "ck_booking_reports_report_kind", "kind", KINDS_BEFORE)
    _allow("bookings", "ck_bookings_booking_status", "status", STATUSES_BEFORE)
