"""account actions

Phase 10, "User management" (CLAUDE.md 6.6, 6.9, 6.11): `account_actions`, one row for each time an account
is suspended, removed or reinstated, with who did it and why. Kept as written: the API's role can add rows
only. Adds the booking status `cancelled_by_admin`, for upcoming bookings cancelled and refunded when an
admin suspends or removes the parent or the sitter (Reuben, 2026-11-22). Like every table: RLS on with no
policies, nothing for the browser roles.

Revision ID: b684c2511e27
Revises: aa0d951a16d9
Create Date: 2026-11-23 09:00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b684c2511e27"
down_revision: Union[str, Sequence[str], None] = "aa0d951a16d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

API_ROLE = "pacifyco_api"
BROWSER_ROLES = ["anon", "authenticated"]

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
    "closed_by_admin",
]
STATUSES_AFTER = [*STATUSES_BEFORE, "cancelled_by_admin"]


def _quoted(values: list[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _allow_statuses(values: list[str]) -> None:
    op.drop_constraint(op.f("ck_bookings_booking_status"), "bookings", type_="check")
    op.create_check_constraint(op.f("ck_bookings_booking_status"), "bookings", f"status IN ({_quoted(values)})")


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
        "account_actions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column(
            "action",
            sa.Enum(
                "suspended",
                "removed",
                "reinstated",
                name="account_action",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "kind",
            sa.Enum(
                "low_ratings",
                "safety",
                "strikes",
                "other",
                name="account_action_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("admin_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "(action = 'reinstated') = (kind IS NULL)", name=op.f("ck_account_actions_kind_unless_reinstated")
        ),
        sa.ForeignKeyConstraint(
            ["admin_id"], ["profiles.id"], name=op.f("fk_account_actions_admin_id_profiles"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["profiles.id"], name=op.f("fk_account_actions_profile_id_profiles"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_actions")),
    )
    op.create_index(
        "ix_account_actions_profile_id_created_at", "account_actions", ["profile_id", "created_at"], unique=False
    )
    _lock_down("account_actions")
    op.execute(f'REVOKE UPDATE, DELETE ON "account_actions" FROM {API_ROLE}')
    _allow_statuses(STATUSES_AFTER)


def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT FROM bookings WHERE status = 'cancelled_by_admin') THEN
            RAISE EXCEPTION 'Bookings were cancelled by an admin; they have nowhere to go back to';
          END IF;
        END $$;
        """
    )
    _allow_statuses(STATUSES_BEFORE)
    op.drop_index("ix_account_actions_profile_id_created_at", table_name="account_actions")
    op.drop_table("account_actions")
