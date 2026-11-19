"""charge upi reference

Paying a charge (CLAUDE.md 6.5; overtime in phase 8): the parent's UPI reference is kept on the charge
row itself, and cleared if an admin rejects it. So the API's role may now update `payments.upi_reference`
too. Amounts still can't change and rows still can't be deleted.

Revision ID: f7b9d1e3a5c6
Revises: e495d3416292
Create Date: 2026-11-19 15:00:00

"""

from typing import Sequence, Union

from alembic import op

revision: str = "f7b9d1e3a5c6"
down_revision: Union[str, Sequence[str], None] = "e495d3416292"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

API_ROLE = "pacifyco_api"


def upgrade() -> None:
    op.execute(f'GRANT UPDATE (upi_reference) ON "payments" TO {API_ROLE}')


def downgrade() -> None:
    op.execute(f'REVOKE UPDATE (upi_reference) ON "payments" FROM {API_ROLE}')
