"""psych tests

Sitter psychology screening (CLAUDE.md section 7 step 5): `psych_tests` and `psych_questions` are
data, read by sitters taking the test; `psych_attempts` and `psych_answers` hold what a sitter wrote.
Not auto-scored -- an admin reads the answers and records pass or fail on the attempt (the admin
verification queue, next).

Seeds one active test, clearly marked as a placeholder (`is_placeholder`), with a few multiple-choice
and short-answer questions so the feature works end to end before a licensed psychologist's real
questions replace it.

Like every table: RLS on with no policies, nothing for the browser roles.

Revision ID: f18db1f7bf01
Revises: 5b2e9d7c41a8
Create Date: 2026-11-03 15:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

BROWSER_ROLES = ["anon", "authenticated"]
QUESTION_KINDS = ["multiple_choice", "short_answer"]
ATTEMPT_STATUSES = ["in_progress", "submitted", "passed", "failed"]

PLACEHOLDER_TEST_ID = "437721b4-f6b3-4293-a544-43b94582dd82"
PLACEHOLDER_PREFIX = "[Placeholder question -- not yet reviewed by a licensed psychologist] "
PLACEHOLDER_QUESTIONS: list[dict] = [
    {
        "order_index": 1,
        "kind": "multiple_choice",
        "prompt": "A child in your care says they fell and scraped their knee a little. What's your first step?",
        "options": [
            "Clean and bandage the scrape, then comfort the child",
            "Call the parent immediately even for a minor scrape",
            "Ignore it, it's just a scrape",
            "Take a photo to show the parent later",
        ],
    },
    {
        "order_index": 2,
        "kind": "multiple_choice",
        "prompt": "You arrive and the home doesn't match what you expected from the listing. What do you do?",
        "options": [
            "Still provide care and raise concerns with Pacify afterwards",
            "Leave immediately without telling anyone",
            "Provide care but say nothing",
            "Ask the child to explain",
        ],
    },
    {
        "order_index": 3,
        "kind": "multiple_choice",
        "prompt": "A child refuses to eat the meal the parent left. How do you respond?",
        "options": [
            "Offer it calmly a couple of times, don't force it, and tell the parent at pickup",
            "Force the child to eat",
            "Give the child something else without telling the parent",
            "Leave the child hungry and move on",
        ],
    },
    {
        "order_index": 4,
        "kind": "short_answer",
        "prompt": "Describe a time you handled a stressful situation involving a child. What did you do?",
        "options": None,
    },
    {
        "order_index": 5,
        "kind": "short_answer",
        "prompt": "Why do you want to work as a babysitter with Pacify?",
        "options": None,
    },
]

# revision identifiers, used by Alembic.
revision: str = "f18db1f7bf01"
down_revision: str | Sequence[str] | None = "5b2e9d7c41a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _lock_down(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    for role in BROWSER_ROLES:
        op.execute(
            f"""
            DO $$ BEGIN
              IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                REVOKE ALL ON "{table}" FROM {role};
              END IF;
            END $$;
            """
        )


def upgrade() -> None:
    op.create_table(
        "psych_tests",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("is_placeholder", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_psych_tests")),
        sa.UniqueConstraint("version", name=op.f("uq_psych_tests_version")),
    )

    op.create_table(
        "psych_questions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("test_id", sa.Uuid(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(*QUESTION_KINDS, name="psych_question_kind", native_enum=False, create_constraint=True, length=32),
            nullable=False,
        ),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("options", sa.ARRAY(sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["test_id"], ["psych_tests.id"], name=op.f("fk_psych_questions_test_id_psych_tests"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_psych_questions")),
        sa.UniqueConstraint("test_id", "order_index", name=op.f("uq_psych_questions_test_id")),
    )
    op.create_index(op.f("ix_psych_questions_test_id"), "psych_questions", ["test_id"], unique=False)

    op.create_table(
        "psych_attempts",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("sitter_id", sa.Uuid(), nullable=False),
        sa.Column("test_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                *ATTEMPT_STATUSES, name="psych_attempt_status", native_enum=False, create_constraint=True, length=32
            ),
            server_default="in_progress",
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["sitter_id"], ["sitters.profile_id"], name=op.f("fk_psych_attempts_sitter_id_sitters"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["test_id"], ["psych_tests.id"], name=op.f("fk_psych_attempts_test_id_psych_tests"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["profiles.id"], name=op.f("fk_psych_attempts_reviewed_by_profiles"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_psych_attempts")),
    )
    op.create_index(op.f("ix_psych_attempts_sitter_id"), "psych_attempts", ["sitter_id"], unique=False)

    op.create_table(
        "psych_answers",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["psych_attempts.id"],
            name=op.f("fk_psych_answers_attempt_id_psych_attempts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["psych_questions.id"],
            name=op.f("fk_psych_answers_question_id_psych_questions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_psych_answers")),
        sa.UniqueConstraint("attempt_id", "question_id", name=op.f("uq_psych_answers_attempt_id")),
    )
    op.create_index(op.f("ix_psych_answers_attempt_id"), "psych_answers", ["attempt_id"], unique=False)

    op.bulk_insert(
        sa.table(
            "psych_tests",
            sa.column("id", sa.Uuid()),
            sa.column("version", sa.Text()),
        ),
        [{"id": PLACEHOLDER_TEST_ID, "version": "placeholder-v1"}],
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
            {
                "test_id": PLACEHOLDER_TEST_ID,
                "order_index": question["order_index"],
                "kind": question["kind"],
                "prompt": PLACEHOLDER_PREFIX + question["prompt"],
                "options": question["options"],
            }
            for question in PLACEHOLDER_QUESTIONS
        ],
    )

    for table in ("psych_tests", "psych_questions", "psych_attempts", "psych_answers"):
        _lock_down(table)


def downgrade() -> None:
    op.drop_index(op.f("ix_psych_answers_attempt_id"), table_name="psych_answers")
    op.drop_table("psych_answers")
    op.drop_index(op.f("ix_psych_attempts_sitter_id"), table_name="psych_attempts")
    op.drop_table("psych_attempts")
    op.drop_index(op.f("ix_psych_questions_test_id"), table_name="psych_questions")
    op.drop_table("psych_questions")
    op.drop_table("psych_tests")
