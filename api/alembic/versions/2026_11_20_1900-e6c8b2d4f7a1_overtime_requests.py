"""overtime requests

Phase 8 (CLAUDE.md 6.8; decided 2026-11-12): during the booking the parent asks for extra whole hours;
the sitter accepts or declines. Nothing is charged here -- overtime is worked out at check-out either way.

Like every table: RLS on with no policies, nothing for the browser roles.

Revision ID: e6c8b2d4f7a1
Revises: d3f5b7a9c1e4
Create Date: 2026-11-20 19:00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e6c8b2d4f7a1"
down_revision: Union[str, Sequence[str], None] = "d3f5b7a9c1e4"
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
        "overtime_requests",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("requested_hours", sa.SmallInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "accepted",
                "declined",
                name="overtime_request_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("requested_hours >= 1", name=op.f("ck_overtime_requests_requested_hours_positive")),
        sa.CheckConstraint(
            "(status = 'pending') = (decided_at IS NULL)", name=op.f("ck_overtime_requests_decided_unless_pending")
        ),
        sa.ForeignKeyConstraint(
            ["booking_id"], ["bookings.id"], name=op.f("fk_overtime_requests_booking_id_bookings"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_overtime_requests")),
    )
    op.create_index(
        "uq_overtime_requests_booking_id_pending",
        "overtime_requests",
        ["booking_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    _lock_down("overtime_requests")


def downgrade() -> None:
    op.drop_index("uq_overtime_requests_booking_id_pending", table_name="overtime_requests")
    op.drop_table("overtime_requests")
