"""Reuben's screening questions (Screening_Questions.docx, 2026-11-13) replace the placeholder psychology
test: 15 statements, each answered on a scale from 1 (least relevant) to 5 (most relevant). A new
question kind, `scale`, and a new active test version; the placeholder test stays (old attempts point
at it) but is no longer active.

Revision ID: b8d2e4f6a1c3
Revises: f9a1c3e5b7d2
Create Date: 2026-11-13 22:00:00
"""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "b8d2e4f6a1c3"
down_revision = "f9a1c3e5b7d2"
branch_labels = None
depends_on = None

KINDS_BEFORE = ("multiple_choice", "short_answer")
KINDS_AFTER = (*KINDS_BEFORE, "scale")

TEST_ID = uuid.UUID("6b1f0c3e-2a4d-4e8b-9c7f-5d3a1e9b0c21")
VERSION = "screening-v1"

# Word for word from Reuben's document, in its order.
STATEMENTS = [
    "I stay calm even when work piles up suddenly.",
    "Small problems at work often ruin my whole day.",
    "I recover quickly after a failure or setback.",
    "If I make a mistake that no one notices, I still own up to it.",
    "If a deadline is impossible, I would rather fake the work than admit I couldn't finish it.",
    "I always follow company rules, even when no one is watching.",
    "I listen carefully before I respond in a disagreement.",
    "I get defensive when someone questions my work.",
    "I try to understand the other person's point of view during a conflict.",
    "I finish what I start, even if the task becomes boring.",
    "I do just enough work to get by.",
    "If I commit to something, I make sure it gets done.",
    "When a plan fails, I quickly find another way to get the result.",
    "I prefer to do things the same way I have always done them.",
    "I am open to feedback that changes how I work.",
]


def _kinds(kinds: tuple[str, ...]) -> None:
    op.drop_constraint(op.f("ck_psych_questions_psych_question_kind"), "psych_questions", type_="check")
    op.create_check_constraint(
        op.f("ck_psych_questions_psych_question_kind"),
        "psych_questions",
        "kind IN ({})".format(", ".join(f"'{kind}'" for kind in kinds)),
    )


def upgrade() -> None:
    _kinds(KINDS_AFTER)
    op.execute("UPDATE psych_tests SET is_active = false")
    op.bulk_insert(
        sa.table(
            "psych_tests",
            sa.column("id", sa.Uuid()),
            sa.column("version", sa.Text()),
            sa.column("is_placeholder", sa.Boolean()),
            sa.column("is_active", sa.Boolean()),
        ),
        [{"id": TEST_ID, "version": VERSION, "is_placeholder": False, "is_active": True}],
    )
    op.bulk_insert(
        sa.table(
            "psych_questions",
            sa.column("test_id", sa.Uuid()),
            sa.column("order_index", sa.Integer()),
            sa.column("kind", sa.Text()),
            sa.column("prompt", sa.Text()),
            sa.column("options", sa.ARRAY(sa.Text())),
        ),
        [
            {"test_id": TEST_ID, "order_index": index, "kind": "scale", "prompt": statement, "options": None}
            for index, statement in enumerate(STATEMENTS, start=1)
        ],
    )


def downgrade() -> None:
    # Attempts at this version go with it (database owner only; development use).
    op.execute(f"DELETE FROM psych_answers WHERE attempt_id IN (SELECT id FROM psych_attempts WHERE test_id = '{TEST_ID}')")
    op.execute(f"DELETE FROM psych_attempts WHERE test_id = '{TEST_ID}'")
    op.execute(f"DELETE FROM psych_tests WHERE id = '{TEST_ID}'")
    op.execute("UPDATE psych_tests SET is_active = true WHERE version = 'placeholder-v1'")
    _kinds(KINDS_BEFORE)
