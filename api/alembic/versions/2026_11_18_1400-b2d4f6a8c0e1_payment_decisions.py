"""payment decisions

Phase 6, "Admin confirms/rejects payments; refunds": the `awaiting_verification` booking status (paid,
waiting for a child's verification; it holds her time, Reuben 2026-11-18) and `payments.transfer_reference`
(the UPI or bank transfer reference a refund was paid back with). The API's role may update that column
too, as part of marking a refund paid; amounts stay unchangeable.

Revision ID: b2d4f6a8c0e1
Revises: a1c3e5f7b9d2
Create Date: 2026-11-18 14:00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2d4f6a8c0e1"
down_revision: Union[str, Sequence[str], None] = "a1c3e5f7b9d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

API_ROLE = "pacifyco_api"
STATUSES_BEFORE = [
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
    "cancelled_unpaid",
    "cancelled_slot_taken",
]
STATUSES_AFTER = [STATUSES_BEFORE[0], "awaiting_verification", *STATUSES_BEFORE[1:]]


def _quoted(values: list[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _allow(values: list[str]) -> None:
    op.drop_constraint(op.f("ck_bookings_booking_status"), "bookings", type_="check")
    op.create_check_constraint(op.f("ck_bookings_booking_status"), "bookings", f"status IN ({_quoted(values)})")


def upgrade() -> None:
    _allow(STATUSES_AFTER)
    op.add_column("payments", sa.Column("transfer_reference", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_payments_refund_paid_has_reference"),
        "payments",
        "kind <> 'refund' OR status <> 'confirmed' OR transfer_reference IS NOT NULL",
    )
    op.execute(f'GRANT UPDATE (transfer_reference) ON "payments" TO {API_ROLE}')


def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT FROM bookings WHERE status = 'awaiting_verification')
             OR EXISTS (SELECT FROM payments WHERE transfer_reference IS NOT NULL) THEN
            RAISE EXCEPTION 'Paid bookings or refund references exist; they have nowhere to go back to';
          END IF;
        END $$;
        """
    )
    op.drop_constraint(op.f("ck_payments_refund_paid_has_reference"), "payments", type_="check")
    op.drop_column("payments", "transfer_reference")
    _allow(STATUSES_BEFORE)
