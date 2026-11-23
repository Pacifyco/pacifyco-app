"""Index the audit log by record id (phase 10: the audit log view and the admin booking page filter by it).

Revision ID: 57155d807f75
Revises: 0e9b936da034
Create Date: 2026-11-23 13:00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "57155d807f75"
down_revision: str | Sequence[str] | None = "0e9b936da034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(op.f("ix_audit_log_entity_id"), "audit_log", ["entity_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_log_entity_id"), table_name="audit_log")
