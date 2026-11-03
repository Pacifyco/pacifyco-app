import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ARRAY, DateTime, ForeignKey, Integer, Text, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import created_at, enum_column, uuid_pk


class PsychQuestionKind(StrEnum):
    multiple_choice = "multiple_choice"
    short_answer = "short_answer"


class PsychAttemptStatus(StrEnum):
    in_progress = "in_progress"
    submitted = "submitted"
    passed = "passed"
    failed = "failed"


class PsychTest(Base):
    """One version of the psychology screening (CLAUDE.md section 7 step 5). Only one is active at a
    time; `is_placeholder` marks the clearly-fake set shipped before a licensed psychologist's
    questions arrive."""

    __tablename__ = "psych_tests"

    id: Mapped[uuid.UUID] = uuid_pk()
    version: Mapped[str] = mapped_column(Text, unique=True)
    is_placeholder: Mapped[bool] = mapped_column(server_default=true())
    is_active: Mapped[bool] = mapped_column(server_default=true())
    created_at: Mapped[datetime] = created_at()


class PsychQuestion(Base):
    __tablename__ = "psych_questions"
    __table_args__ = (UniqueConstraint("test_id", "order_index"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("psych_tests.id", ondelete="CASCADE"), index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    kind: Mapped[PsychQuestionKind] = mapped_column(enum_column(PsychQuestionKind, "psych_question_kind"))
    prompt: Mapped[str] = mapped_column(Text)
    # Choices for a multiple_choice question; null for short_answer.
    options: Mapped[list[str] | None] = mapped_column(ARRAY(Text))


class PsychAttempt(Base):
    """One sitter's attempt at a test version. Not auto-scored: an admin reads the answers and
    records pass or fail (CLAUDE.md 7 step 5)."""

    __tablename__ = "psych_attempts"

    id: Mapped[uuid.UUID] = uuid_pk()
    sitter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sitters.profile_id", ondelete="CASCADE"), index=True)
    test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("psych_tests.id", ondelete="RESTRICT"))
    status: Mapped[PsychAttemptStatus] = mapped_column(
        enum_column(PsychAttemptStatus, "psych_attempt_status"), server_default=PsychAttemptStatus.in_progress.value
    )
    started_at: Mapped[datetime] = created_at()
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class PsychAnswer(Base):
    __tablename__ = "psych_answers"
    __table_args__ = (UniqueConstraint("attempt_id", "question_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("psych_attempts.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("psych_questions.id", ondelete="RESTRICT"))
    answer_text: Mapped[str] = mapped_column(Text)
