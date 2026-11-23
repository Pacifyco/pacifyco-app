"""complaints and grievances

Phase 10, "Complaints and grievances" (CLAUDE.md 6.12; Reuben, 2026-11-23):

- Complaints get their targets (`reply_by` 24 hours, `resolve_by` 48 hours, 15 days once an admin marks it a
  serious safety matter, or an appeal's 7 working days), when it happened, what the admin did, escalation to
  the Grievance Officer (overdue, or the person disagrees) and the officer's written decision.
- An appeal is a complaint of type `suspension`, linked to the `account_actions` row it's against (one appeal
  per decision), with its outcome.
- `complaint_messages`: the written thread between the person and Pacifyco. Append-only.
- `public_holidays`: added by admins; not working days when counting an appeal's 7 working days.
- Documents can be a complaint's attachment (`complaint_attachment`, with `complaint_id`).

Existing complaints (the Issues button) get targets counted from when they were raised.

Revision ID: d5c427c83be2
Revises: 57155d807f75
Create Date: 2026-11-23 15:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5c427c83be2"
down_revision: str | Sequence[str] | None = "57155d807f75"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

API_ROLE = "pacifyco_api"
BROWSER_ROLES = ("anon", "authenticated")
DOCUMENT_TYPES = [
    "birth_certificate",
    "government_id",
    "college_or_work_id",
    "police_certificate",
    "first_aid_certificate",
    "doctor_note",
    "photo",
]
COMPLAINT_CHECKS = {
    "ck_complaints_appeal_outcome": "appeal_outcome IN ('upheld', 'rejected')",
    "ck_complaints_appeal_has_decision": "(type = 'suspension') = (account_action_id IS NOT NULL)",
    "ck_complaints_outcome_only_on_appeals": "appeal_outcome IS NULL OR type = 'suspension'",
    "ck_complaints_escalated_status": "(escalated_at IS NULL) OR status IN ('escalated', 'closed')",
    "ck_complaints_officer_decision_has_text": "(officer_decided_at IS NULL) = (officer_decision IS NULL)",
}
NEW_COLUMNS = [
    "happened_on",
    "serious",
    "reply_by",
    "resolve_by",
    "resolution",
    "account_action_id",
    "appeal_outcome",
    "escalated_at",
    "escalated_by",
    "escalation_note",
    "officer_acknowledged_at",
    "officer_id",
    "officer_decision",
    "officer_decided_at",
]
FOREIGN_KEYS = [  # (name, column, table)
    ("fk_complaints_officer_id_profiles", "officer_id", "profiles"),
    ("fk_complaints_escalated_by_profiles", "escalated_by", "profiles"),
    ("fk_complaints_account_action_id_account_actions", "account_action_id", "account_actions"),
]


def _lock_down(table: str) -> None:
    """Row Level Security with no policies, and nothing for the browser roles (CLAUDE.md 5)."""
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


def _document_types(values: list[str]) -> None:
    op.drop_constraint(op.f("ck_documents_document_type"), "documents", type_="check")
    quoted = ", ".join(f"'{value}'" for value in values)
    op.create_check_constraint(op.f("ck_documents_document_type"), "documents", f"type IN ({quoted})")


def upgrade() -> None:
    op.create_table(
        "public_holidays",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.CheckConstraint("name <> ''", name=op.f("ck_public_holidays_name_not_empty")),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_public_holidays")),
    )
    op.create_table(
        "complaint_messages",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("complaint_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("body <> ''", name=op.f("ck_complaint_messages_body_not_empty")),
        sa.ForeignKeyConstraint(
            ["author_id"], ["profiles.id"], name=op.f("fk_complaint_messages_author_id_profiles"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["complaint_id"],
            ["complaints.id"],
            name=op.f("fk_complaint_messages_complaint_id_complaints"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_complaint_messages")),
    )
    op.create_index(op.f("ix_complaint_messages_complaint_id"), "complaint_messages", ["complaint_id"])
    _lock_down("public_holidays")
    _lock_down("complaint_messages")
    op.execute(f'REVOKE UPDATE, DELETE ON "complaint_messages" FROM {API_ROLE}')

    op.add_column("complaints", sa.Column("happened_on", sa.Date(), nullable=True))
    op.add_column("complaints", sa.Column("serious", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("complaints", sa.Column("reply_by", sa.DateTime(timezone=True), nullable=True))
    op.add_column("complaints", sa.Column("resolve_by", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE complaints SET reply_by = created_at + interval '24 hours', resolve_by = created_at + interval '48 hours'"
    )
    op.alter_column("complaints", "reply_by", nullable=False)
    op.alter_column("complaints", "resolve_by", nullable=False)
    op.add_column("complaints", sa.Column("resolution", sa.Text(), nullable=True))
    op.add_column("complaints", sa.Column("account_action_id", sa.Uuid(), nullable=True))
    op.add_column("complaints", sa.Column("appeal_outcome", sa.String(length=32), nullable=True))
    op.add_column("complaints", sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("complaints", sa.Column("escalated_by", sa.Uuid(), nullable=True))
    op.add_column("complaints", sa.Column("escalation_note", sa.Text(), nullable=True))
    op.add_column("complaints", sa.Column("officer_acknowledged_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("complaints", sa.Column("officer_id", sa.Uuid(), nullable=True))
    op.add_column("complaints", sa.Column("officer_decision", sa.Text(), nullable=True))
    op.add_column("complaints", sa.Column("officer_decided_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_complaints_raised_by", "complaints", ["raised_by"])
    op.create_unique_constraint(op.f("uq_complaints_account_action_id"), "complaints", ["account_action_id"])
    for name, column, table in FOREIGN_KEYS:
        op.create_foreign_key(op.f(name), "complaints", table, [column], ["id"], ondelete="RESTRICT")
    for name, condition in COMPLAINT_CHECKS.items():
        op.create_check_constraint(op.f(name), "complaints", condition)

    _document_types([*DOCUMENT_TYPES, "complaint_attachment"])
    op.add_column("documents", sa.Column("complaint_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_documents_complaint_id"), "documents", ["complaint_id"])
    op.create_foreign_key(
        op.f("fk_documents_complaint_id_complaints"),
        "documents",
        "complaints",
        ["complaint_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_documents_attachment_has_complaint"),
        "documents",
        "(type = 'complaint_attachment') = (complaint_id IS NOT NULL)",
    )


def downgrade() -> None:
    used = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT (SELECT count(*) FROM documents WHERE complaint_id IS NOT NULL)"
                " + (SELECT count(*) FROM complaints WHERE type = 'suspension')"
                " + (SELECT count(*) FROM complaint_messages)"
            )
        )
        .scalar_one()
    )
    if used:
        raise RuntimeError("Complaints have attachments, appeals or messages; downgrading would lose them.")

    op.drop_constraint(op.f("ck_documents_attachment_has_complaint"), "documents", type_="check")
    op.drop_constraint(op.f("fk_documents_complaint_id_complaints"), "documents", type_="foreignkey")
    op.drop_index(op.f("ix_documents_complaint_id"), table_name="documents")
    op.drop_column("documents", "complaint_id")
    _document_types(DOCUMENT_TYPES)

    for name in COMPLAINT_CHECKS:
        op.drop_constraint(op.f(name), "complaints", type_="check")
    for name, _, _ in FOREIGN_KEYS:
        op.drop_constraint(op.f(name), "complaints", type_="foreignkey")
    op.drop_constraint(op.f("uq_complaints_account_action_id"), "complaints", type_="unique")
    op.drop_index("ix_complaints_raised_by", table_name="complaints")
    for column in reversed(NEW_COLUMNS):
        op.drop_column("complaints", column)

    op.drop_index(op.f("ix_complaint_messages_complaint_id"), table_name="complaint_messages")
    op.drop_table("complaint_messages")
    op.drop_table("public_holidays")
