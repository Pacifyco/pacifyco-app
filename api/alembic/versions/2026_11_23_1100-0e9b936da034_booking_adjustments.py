"""booking adjustments

Phase 10, "Bookings overview and manual adjustments" (Reuben, 2026-11-23):

- An admin can waive an unpaid overtime or cancellation charge, with a reason: payment status `waived` and
  `payments.waive_reason` (the API's role may set it, as it does the other decision columns).
- An admin can add extra pay for the sitter on a booking: earning kind `adjustment`, with a `note` she sees.
  Any number per booking, so the one-of-each-kind index now leaves adjustments out.

Amounts still can't change and rows still can't be deleted.

Revision ID: 0e9b936da034
Revises: b684c2511e27
Create Date: 2026-11-23 11:00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0e9b936da034"
down_revision: Union[str, Sequence[str], None] = "b684c2511e27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

API_ROLE = "pacifyco_api"


def _allow(table: str, constraint: str, column: str, values: list[str]) -> None:
    op.drop_constraint(op.f(constraint), table, type_="check")
    quoted = ", ".join(f"'{value}'" for value in values)
    op.create_check_constraint(op.f(constraint), table, f"{column} IN ({quoted})")


def upgrade() -> None:
    op.add_column("payments", sa.Column("waive_reason", sa.Text(), nullable=True))
    _allow("payments", "ck_payments_payment_status", "status", ["pending", "confirmed", "rejected", "waived"])
    op.create_check_constraint(
        op.f("ck_payments_waived_has_reason"), "payments", "(status = 'waived') = (waive_reason IS NOT NULL)"
    )
    op.create_check_constraint(
        op.f("ck_payments_only_charges_waived"),
        "payments",
        "status <> 'waived' OR kind IN ('overtime', 'cancellation_charge')",
    )
    op.execute(f'GRANT UPDATE (waive_reason) ON "payments" TO {API_ROLE}')

    op.add_column("sitter_earnings", sa.Column("note", sa.Text(), nullable=True))
    _allow(
        "sitter_earnings",
        "ck_sitter_earnings_earning_kind",
        "kind",
        ["booking", "overtime", "show_up_fee", "adjustment"],
    )
    op.create_check_constraint(
        op.f("ck_sitter_earnings_adjustment_has_note"),
        "sitter_earnings",
        "(kind = 'adjustment') = (note IS NOT NULL)",
    )
    op.drop_index("uq_sitter_earnings_booking_id_kind", table_name="sitter_earnings")
    op.create_index(
        "uq_sitter_earnings_booking_id_kind",
        "sitter_earnings",
        ["booking_id", "kind"],
        unique=True,
        postgresql_where=sa.text("kind <> 'adjustment'"),
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT FROM payments WHERE status = 'waived')
             OR EXISTS (SELECT FROM sitter_earnings WHERE kind = 'adjustment') THEN
            RAISE EXCEPTION 'Charges were waived or pay adjusted; they have nowhere to go back to';
          END IF;
        END $$;
        """
    )
    op.drop_index("uq_sitter_earnings_booking_id_kind", table_name="sitter_earnings")
    op.create_index("uq_sitter_earnings_booking_id_kind", "sitter_earnings", ["booking_id", "kind"], unique=True)
    op.drop_constraint(op.f("ck_sitter_earnings_adjustment_has_note"), "sitter_earnings", type_="check")
    _allow("sitter_earnings", "ck_sitter_earnings_earning_kind", "kind", ["booking", "overtime", "show_up_fee"])
    op.drop_column("sitter_earnings", "note")

    op.execute(f'REVOKE UPDATE (waive_reason) ON "payments" FROM {API_ROLE}')
    op.drop_constraint(op.f("ck_payments_only_charges_waived"), "payments", type_="check")
    op.drop_constraint(op.f("ck_payments_waived_has_reason"), "payments", type_="check")
    _allow("payments", "ck_payments_payment_status", "status", ["pending", "confirmed", "rejected"])
    op.drop_column("payments", "waive_reason")
