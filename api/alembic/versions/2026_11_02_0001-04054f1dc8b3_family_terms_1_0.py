"""family terms 1.0

Publishes the Pacifyco Family Terms of Use v1.0 (web/src/content/family-terms-v1.0.md) as the parent
terms, replacing the 0.1 draft. It takes effect at once: no parent has relied on the draft (it was
marked "DRAFT — NOT LEGALLY REVIEWED"), so the 14-day notice for changes doesn't apply. Parents who
accepted the draft are asked to accept v1.0 before their next action that matters.

Revision ID: 04054f1dc8b3
Revises: 2fc64a34e0d2
Create Date: 2026-11-02 00:01:00

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "04054f1dc8b3"
down_revision: str | Sequence[str] | None = "2fc64a34e0d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO legal_documents (kind, version, effective_at, content_path)
        VALUES ('parent_terms', '1.0', now(), 'web/src/content/family-terms-v1.0.md')
        """
    )


def downgrade() -> None:
    # Acceptances of v1.0 go with it (only possible as the database owner; development use).
    op.execute(
        """
        DELETE FROM legal_acceptances WHERE document_id IN
          (SELECT id FROM legal_documents WHERE kind = 'parent_terms' AND version = '1.0')
        """
    )
    op.execute("DELETE FROM legal_documents WHERE kind = 'parent_terms' AND version = '1.0'")
