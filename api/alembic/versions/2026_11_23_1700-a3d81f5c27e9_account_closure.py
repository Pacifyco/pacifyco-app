"""account closure and data requests

Phase 10, "Sitter account closure; data access, correction and deletion requests" (CLAUDE.md 6.13; Reuben,
2026-11-23):

- Parents and sitters can close their own account: profile status `closed`, and an `account_actions` row
  `closed` (no admin, no kind). An admin can reopen it (a `reinstated` row, as before).
- A data request is a complaint of type `data_request` with what's asked for: `request_kind` access,
  correction or deletion. An admin handles it by hand.

Revision ID: a3d81f5c27e9
Revises: d5c427c83be2
Create Date: 2026-11-23 17:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3d81f5c27e9"
down_revision: str | Sequence[str] | None = "d5c427c83be2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = ["pending", "active", "suspended", "removed"]
ACTIONS = ["suspended", "removed", "reinstated"]


def _allow(table: str, constraint: str, column: str, values: list[str]) -> None:
    op.drop_constraint(op.f(constraint), table, type_="check")
    quoted = ", ".join(f"'{value}'" for value in values)
    op.create_check_constraint(op.f(constraint), table, f"{column} IN ({quoted})")


def upgrade() -> None:
    _allow("profiles", "ck_profiles_profile_status", "status", [*STATUSES, "closed"])
    _allow("account_actions", "ck_account_actions_account_action", "action", [*ACTIONS, "closed"])
    op.drop_constraint(op.f("ck_account_actions_kind_unless_reinstated"), "account_actions", type_="check")
    op.create_check_constraint(
        op.f("ck_account_actions_kind_when_blocked"),
        "account_actions",
        "(action IN ('suspended', 'removed')) = (kind IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_account_actions_closed_by_the_person"), "account_actions", "action <> 'closed' OR admin_id IS NULL"
    )

    op.add_column("complaints", sa.Column("request_kind", sa.String(length=32), nullable=True))
    op.create_check_constraint(
        op.f("ck_complaints_data_request_kind"), "complaints", "request_kind IN ('access', 'correction', 'deletion')"
    )
    op.create_check_constraint(
        op.f("ck_complaints_data_request_has_kind"),
        "complaints",
        "(type = 'data_request') = (request_kind IS NOT NULL)",
    )


def downgrade() -> None:
    used = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT (SELECT count(*) FROM profiles WHERE status = 'closed')"
                " + (SELECT count(*) FROM account_actions WHERE action = 'closed')"
                " + (SELECT count(*) FROM complaints WHERE type = 'data_request')"
            )
        )
        .scalar_one()
    )
    if used:
        raise RuntimeError("Closed accounts or data requests exist; downgrading would lose them.")

    op.drop_constraint(op.f("ck_complaints_data_request_has_kind"), "complaints", type_="check")
    op.drop_constraint(op.f("ck_complaints_data_request_kind"), "complaints", type_="check")
    op.drop_column("complaints", "request_kind")

    op.drop_constraint(op.f("ck_account_actions_closed_by_the_person"), "account_actions", type_="check")
    op.drop_constraint(op.f("ck_account_actions_kind_when_blocked"), "account_actions", type_="check")
    op.create_check_constraint(
        op.f("ck_account_actions_kind_unless_reinstated"), "account_actions", "(action = 'reinstated') = (kind IS NULL)"
    )
    _allow("account_actions", "ck_account_actions_account_action", "action", ACTIONS)
    _allow("profiles", "ck_profiles_profile_status", "status", STATUSES)
