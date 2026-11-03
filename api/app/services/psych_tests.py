"""Sitter psychology screening (CLAUDE.md section 7 step 5): multiple-choice and short-answer
questions, taken in the app. Not auto-scored -- an admin reads the answers and records pass or
fail, which the admin verification queue (next) reads back. Only `passed` unlocks that step.

The sitter-facing functions never take an attempt id: they always work against "my current
attempt" so there's nothing for one sitter to guess into another's (no IDOR surface to begin
with). Admin functions take the attempt id explicitly, since an admin reviews a specific attempt.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import PsychAnswer, PsychAttempt, PsychAttemptStatus, PsychQuestion, PsychTest
from app.services import audit


def get_active_test(db: Session) -> PsychTest:
    test = db.scalar(select(PsychTest).where(PsychTest.is_active.is_(True)).order_by(PsychTest.created_at.desc()))
    if test is None:  # a migration always seeds one; this means the database is out of date
        raise AppError(
            503, "psych_test_unavailable", "The psychology test isn't available right now. Please try again later."
        )
    return test


def list_questions(db: Session, test_id: uuid.UUID) -> list[PsychQuestion]:
    return list(
        db.scalars(select(PsychQuestion).where(PsychQuestion.test_id == test_id).order_by(PsychQuestion.order_index))
    )


def list_answers(db: Session, attempt_id: uuid.UUID) -> dict[uuid.UUID, str]:
    rows = db.scalars(select(PsychAnswer).where(PsychAnswer.attempt_id == attempt_id))
    return {row.question_id: row.answer_text for row in rows}


def latest_attempt(db: Session, sitter_id: uuid.UUID) -> PsychAttempt | None:
    return db.scalar(
        select(PsychAttempt).where(PsychAttempt.sitter_id == sitter_id).order_by(PsychAttempt.started_at.desc())
    )


def _open_attempt(db: Session, sitter_id: uuid.UUID) -> PsychAttempt | None:
    attempt = latest_attempt(db, sitter_id)
    return attempt if attempt is not None and attempt.status == PsychAttemptStatus.in_progress else None


def start_or_resume_attempt(db: Session, sitter_id: uuid.UUID) -> PsychAttempt:
    """The attempt to write to right now: her open one, or a fresh one against the active test.
    A passed attempt stands -- she can't start another. Retaking after a fail isn't in CLAUDE.md;
    allowed for now (flagged in progress.md as an assumption to confirm with Reuben)."""
    open_attempt = _open_attempt(db, sitter_id)
    if open_attempt is not None:
        return open_attempt
    current = latest_attempt(db, sitter_id)
    if current is not None and current.status in (PsychAttemptStatus.submitted, PsychAttemptStatus.passed):
        return current
    test = get_active_test(db)
    attempt = PsychAttempt(sitter_id=sitter_id, test_id=test.id)
    db.add(attempt)
    db.commit()
    return attempt


@dataclass(frozen=True)
class AnswerIn:
    question_id: uuid.UUID
    answer_text: str


def save_my_answers(db: Session, sitter_id: uuid.UUID, answers: list[AnswerIn]) -> PsychAttempt:
    attempt = start_or_resume_attempt(db, sitter_id)
    if attempt.status != PsychAttemptStatus.in_progress:
        raise AppError(409, "attempt_not_open", "This attempt has already been submitted")

    question_ids = {question.id for question in list_questions(db, attempt.test_id)}
    for answer in answers:
        if answer.question_id not in question_ids:
            raise AppError(422, "invalid_question", "That question isn't part of this test")

    existing = {
        row.question_id: row for row in db.scalars(select(PsychAnswer).where(PsychAnswer.attempt_id == attempt.id))
    }
    for answer in answers:
        cleaned = answer.answer_text.strip()
        if answer.question_id in existing:
            existing[answer.question_id].answer_text = cleaned
        else:
            db.add(PsychAnswer(attempt_id=attempt.id, question_id=answer.question_id, answer_text=cleaned))
    db.commit()
    return attempt


def submit_my_attempt(db: Session, sitter_id: uuid.UUID) -> PsychAttempt:
    attempt = _open_attempt(db, sitter_id)
    if attempt is None:
        raise AppError(409, "attempt_not_open", "There's no test in progress to submit")

    questions = list_questions(db, attempt.test_id)
    answers = list_answers(db, attempt.id)
    unanswered = [question for question in questions if not answers.get(question.id)]
    if unanswered:
        raise AppError(422, "incomplete", "Please answer every question before submitting")

    attempt.status = PsychAttemptStatus.submitted
    attempt.submitted_at = datetime.now(UTC)
    db.commit()
    return attempt


# ---------- admin review (CLAUDE.md section 7 step 5) ----------


def list_for_review(db: Session, status: PsychAttemptStatus = PsychAttemptStatus.submitted) -> list[PsychAttempt]:
    return list(
        db.scalars(select(PsychAttempt).where(PsychAttempt.status == status).order_by(PsychAttempt.submitted_at))
    )


def get_attempt(db: Session, attempt_id: uuid.UUID) -> PsychAttempt:
    attempt = db.get(PsychAttempt, attempt_id)
    if attempt is None:
        raise AppError(404, "not_found", "That attempt doesn't exist")
    return attempt


def record_decision(
    db: Session, admin_id: uuid.UUID, attempt_id: uuid.UUID, passed: bool, notes: str | None
) -> PsychAttempt:
    attempt = get_attempt(db, attempt_id)
    if attempt.status != PsychAttemptStatus.submitted:
        raise AppError(409, "not_submitted", "This attempt hasn't been submitted yet")

    before = {"status": attempt.status.value}
    attempt.status = PsychAttemptStatus.passed if passed else PsychAttemptStatus.failed
    attempt.reviewed_by = admin_id
    attempt.reviewed_at = datetime.now(UTC)
    attempt.notes = notes
    audit.record(
        db,
        admin_id,
        "psych_attempt_reviewed",
        "psych_attempts",
        str(attempt.id),
        before=before,
        after={"status": attempt.status.value},
    )
    db.commit()
    return attempt
