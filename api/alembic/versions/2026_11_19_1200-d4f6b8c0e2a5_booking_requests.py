"""booking requests

The sitter accepts before the parent pays (CLAUDE.md 6.4; Reuben, 2026-11-19). New statuses `requested`
(waiting for her answer), `request_declined` and `request_lapsed`; new bookings start as `requested`.
`request_visible_at` is when she could first see the request (every child on it verified); her 5 hours
to answer run from then. Existing bookings keep their statuses.

Revision ID: d4f6b8c0e2a5
Revises: c3e5a7b9d1f4
Create Date: 2026-11-19 12:00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4f6b8c0e2a5"
down_revision: Union[str, Sequence[str], None] = "c3e5a7b9d1f4"
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
    "cancelled_unverified",
]
AFTER = ["requested", "request_declined", "request_lapsed", *BEFORE]


def _quoted(values: list[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _allow(values: list[str]) -> None:
    op.drop_constraint(op.f("ck_bookings_booking_status"), "bookings", type_="check")
    op.create_check_constraint(op.f("ck_bookings_booking_status"), "bookings", f"status IN ({_quoted(values)})")


def upgrade() -> None:
    _allow(AFTER)
    op.alter_column("bookings", "status", server_default="requested")
    op.add_column("bookings", sa.Column("request_visible_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Requests have no earlier status to go back to (a request isn't waiting for payment), so this refuses
    # while any booking has one.
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT FROM bookings WHERE status IN ('requested', 'request_declined', 'request_lapsed')) THEN
            RAISE EXCEPTION 'Booking requests exist; they have no earlier status to go back to';
          END IF;
        END $$;
        """
    )
    op.drop_column("bookings", "request_visible_at")
    op.alter_column("bookings", "status", server_default="pending_payment")
    _allow(BEFORE)
