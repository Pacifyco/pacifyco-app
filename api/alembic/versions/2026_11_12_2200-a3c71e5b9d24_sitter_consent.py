"""sitter consent

Decided 2026-11-12 (Reuben): the terms and privacy policy are ticked on the consent pages, not at
sign-up, and sitters get a consent page of their own (web/src/content/sitter-consent-v1.0.md, from
Reuben's "Sitter consent" document). It's a versioned document accepted by click-wrap like the terms,
so it's a new `legal_documents` kind; acceptances are `legal_acceptances` rows.

Revision ID: a3c71e5b9d24
Revises: d5577de53ca1
Create Date: 2026-11-12 22:00:00

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3c71e5b9d24"
down_revision: str | Sequence[str] | None = "d5577de53ca1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS_BEFORE = ("parent_terms", "sitter_terms", "privacy_policy")
KINDS_AFTER = (*KINDS_BEFORE, "sitter_consent")


def _check(kinds: tuple[str, ...]) -> None:
    op.drop_constraint(op.f("ck_legal_documents_legal_document_kind"), "legal_documents", type_="check")
    op.create_check_constraint(
        op.f("ck_legal_documents_legal_document_kind"),
        "legal_documents",
        "kind IN ({})".format(", ".join(f"'{kind}'" for kind in kinds)),
    )


def upgrade() -> None:
    _check(KINDS_AFTER)
    op.execute(
        """
        INSERT INTO legal_documents (kind, version, effective_at, content_path)
        VALUES ('sitter_consent', '1.0', now(), 'web/src/content/sitter-consent-v1.0.md')
        """
    )


def downgrade() -> None:
    # Acceptances go with it (only possible as the database owner; development use).
    op.execute(
        """
        DELETE FROM legal_acceptances WHERE document_id IN
          (SELECT id FROM legal_documents WHERE kind = 'sitter_consent')
        """
    )
    op.execute("DELETE FROM legal_documents WHERE kind = 'sitter_consent'")
    _check(KINDS_BEFORE)
