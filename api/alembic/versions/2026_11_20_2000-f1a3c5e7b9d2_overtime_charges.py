"""overtime charges

Phase 8 (CLAUDE.md 6.8): worked out at check-out, whether or not a request was ever made or accepted.
Checked-out time past the booked end is rounded up to the full hour and charged, at the plan's price or
the next tier's for hours past the plan's own latest end; she's paid her own level pay either way. The
charge is a record of how the amount was worked out; its payment is a separate `payments` row (kind
`overtime`).

Like every table: RLS on with no policies, nothing for the browser roles.

Revision ID: f1a3c5e7b9d2
Revises: e6c8b2d4f7a1
Create Date: 2026-11-20 20:00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a3c5e7b9d2"
down_revision: Union[str, Sequence[str], None] = "e6c8b2d4f7a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BROWSER_ROLES = ["anon", "authenticated"]


def _lock_down(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    for role in BROWSER_ROLES:
        op.execute(
            f"""
            DO $$ BEGIN
              IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                REVOKE ALL ON {table} FROM {role};
              END IF;
            END $$;
            """
        )


def upgrade() -> None:
    op.create_table(
        "overtime_charges",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("minutes_over", sa.Integer(), nullable=False),
        sa.Column("hours_charged", sa.SmallInteger(), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("sitter_pay_paise", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("minutes_over >= 0", name=op.f("ck_overtime_charges_minutes_over_not_negative")),
        sa.CheckConstraint("hours_charged >= 1", name=op.f("ck_overtime_charges_hours_charged_positive")),
        sa.CheckConstraint("amount_paise >= 0", name=op.f("ck_overtime_charges_amount_paise_not_negative")),
        sa.CheckConstraint(
            "sitter_pay_paise >= 0", name=op.f("ck_overtime_charges_sitter_pay_paise_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["booking_id"], ["bookings.id"], name=op.f("fk_overtime_charges_booking_id_bookings"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_overtime_charges")),
    )
    op.create_index("uq_overtime_charges_booking_id", "overtime_charges", ["booking_id"], unique=True)
    _lock_down("overtime_charges")


def downgrade() -> None:
    op.drop_index("uq_overtime_charges_booking_id", table_name="overtime_charges")
    op.drop_table("overtime_charges")
