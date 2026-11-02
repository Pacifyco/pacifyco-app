"""drop sitter rate

Sitters no longer set their own hourly rate (Reuben, 2026-11-03): pay is fixed by the sitter's level
(Pause ₹200, Unwind ₹300, Recharge ₹400 an hour; CLAUDE.md 6.2). Drops `sitters.hourly_rate_paise` and
its ₹80-120 check. Downgrading brings the column back empty.

Revision ID: 5b2e9d7c41a8
Revises: a3f8c1d9e204
Create Date: 2026-11-03 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5b2e9d7c41a8"
down_revision: str | Sequence[str] | None = "a3f8c1d9e204"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_sitters_hourly_rate_range"), "sitters", type_="check")
    op.drop_column("sitters", "hourly_rate_paise")


def downgrade() -> None:
    op.add_column("sitters", sa.Column("hourly_rate_paise", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_sitters_hourly_rate_range"), "sitters", "hourly_rate_paise BETWEEN 8000 AND 12000"
    )
