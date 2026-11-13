"""The brand is "Pacifyco" everywhere (Reuben, 2026-11-13): update the placeholder psychology-test
questions seeded in f18db1f7bf01, which say "Pacify".

Revision ID: c4e8b2a6d1f3
Revises: a3c71e5b9d24
Create Date: 2026-11-13 18:00:00
"""

from alembic import op

revision = "c4e8b2a6d1f3"
down_revision = "a3c71e5b9d24"
branch_labels = None
depends_on = None


def _rename(old: str, new: str) -> None:
    # \m and \M are word boundaries, so "Pacifyco" is never renamed again.
    op.execute(
        f"""
        UPDATE psych_questions
        SET prompt = regexp_replace(prompt, '\\m{old}\\M', '{new}', 'g'),
            options = CASE WHEN options IS NULL THEN NULL ELSE ARRAY(
                SELECT regexp_replace(option, '\\m{old}\\M', '{new}', 'g')
                FROM unnest(options) WITH ORDINALITY AS item(option, position)
                ORDER BY position
            ) END
        """
    )


def upgrade() -> None:
    _rename("Pacify", "Pacifyco")


def downgrade() -> None:
    _rename("Pacifyco", "Pacify")
