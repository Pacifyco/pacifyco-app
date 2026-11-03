"""remove aadhaar

Pacifyco no longer collects Aadhaar details at all (Reuben, 2026-11-03: "we will not be taking
aadhaar details anymore"). Drops the `aadhaar_masked` document type and, with it, the
`single_parent_declaration` consent kind, which existed only to stand in for a second masked
Aadhaar upload (CLAUDE.md section 7). Family Terms 2.2 still describes collecting it; that's
flagged in progress.md for a new terms version.

Deletes any existing rows of these kinds first (and their document_access_log rows, since that FK
is RESTRICT) so the narrower CHECK constraints apply cleanly -- staging only, nothing in production
yet. Downgrading restores the wider constraints but not the deleted rows, same as other migrations
here that narrow a choice.

Revision ID: 7c4e9a21f6b3
Revises: f18db1f7bf01
Create Date: 2026-11-03 18:00:00

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c4e9a21f6b3"
down_revision: str | Sequence[str] | None = "f18db1f7bf01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DOCUMENT_TYPES_BEFORE = (
    "aadhaar_masked, birth_certificate, government_id, college_or_work_id, police_certificate, "
    "first_aid_certificate, doctor_note, photo"
)
DOCUMENT_TYPES_AFTER = (
    "birth_certificate, government_id, college_or_work_id, police_certificate, first_aid_certificate, "
    "doctor_note, photo"
)
CONSENT_KINDS_BEFORE = (
    "own_data, child_data, share_care_details, emergency_authorisation, marketing, single_parent_declaration"
)
CONSENT_KINDS_AFTER = "own_data, child_data, share_care_details, emergency_authorisation, marketing"


def _quoted(csv: str) -> str:
    return ", ".join(f"'{value.strip()}'" for value in csv.split(","))


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM document_access_log
        WHERE document_id IN (SELECT id FROM documents WHERE type = 'aadhaar_masked')
        """
    )
    op.execute("DELETE FROM documents WHERE type = 'aadhaar_masked'")
    op.drop_constraint(op.f("ck_documents_document_type"), "documents", type_="check")
    op.create_check_constraint(
        op.f("ck_documents_document_type"), "documents", f"type IN ({_quoted(DOCUMENT_TYPES_AFTER)})"
    )

    op.execute("DELETE FROM consents WHERE kind = 'single_parent_declaration'")
    op.drop_constraint(op.f("ck_consents_consent_kind"), "consents", type_="check")
    op.create_check_constraint(
        op.f("ck_consents_consent_kind"), "consents", f"kind IN ({_quoted(CONSENT_KINDS_AFTER)})"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_consents_consent_kind"), "consents", type_="check")
    op.create_check_constraint(
        op.f("ck_consents_consent_kind"), "consents", f"kind IN ({_quoted(CONSENT_KINDS_BEFORE)})"
    )

    op.drop_constraint(op.f("ck_documents_document_type"), "documents", type_="check")
    op.create_check_constraint(
        op.f("ck_documents_document_type"), "documents", f"type IN ({_quoted(DOCUMENT_TYPES_BEFORE)})"
    )
