"""The admin area. Every route here is for admins only (CLAUDE.md 9: wrong role gets 403)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth import require_role
from app.deps import DbSession
from app.models import Profile, PsychAttemptStatus, PsychQuestionKind, Role
from app.services import documents
from app.services import psych_tests as psych_tests_service
from app.services.storage import StorageClient, get_storage

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role(Role.admin))])
Admin = Annotated[Profile, Depends(require_role(Role.admin))]
Storage = Annotated[StorageClient, Depends(get_storage)]


class DocumentViewUrl(BaseModel):
    url: str


@router.get("/documents/{document_id}/view-url")
def document_view_url(document_id: uuid.UUID, admin: Admin, db: DbSession, storage: Storage) -> DocumentViewUrl:
    """A short-lived signed URL to view one document. Every call is logged (CLAUDE.md 5)."""
    return DocumentViewUrl(url=documents.get_view_url(db, storage, admin.id, document_id))


# ---------- psychology test review (CLAUDE.md section 7 step 5) ----------


class PsychAttemptSummary(BaseModel):
    id: uuid.UUID
    sitter_id: uuid.UUID
    sitter_name: str
    status: PsychAttemptStatus
    submitted_at: datetime | None


def _sitter_names(db: DbSession, sitter_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not sitter_ids:
        return {}
    rows = db.execute(select(Profile.id, Profile.full_name).where(Profile.id.in_(sitter_ids)))
    return dict(rows.all())


@router.get("/psych-attempts")
def list_psych_attempts(
    admin: Admin, db: DbSession, status: PsychAttemptStatus = PsychAttemptStatus.submitted
) -> list[PsychAttemptSummary]:
    attempts = psych_tests_service.list_for_review(db, status)
    names = _sitter_names(db, [attempt.sitter_id for attempt in attempts])
    return [
        PsychAttemptSummary(
            id=attempt.id,
            sitter_id=attempt.sitter_id,
            sitter_name=names.get(attempt.sitter_id, ""),
            status=attempt.status,
            submitted_at=attempt.submitted_at,
        )
        for attempt in attempts
    ]


class PsychAttemptAnswerOut(BaseModel):
    question_id: uuid.UUID
    kind: PsychQuestionKind
    prompt: str
    options: list[str] | None
    answer_text: str | None


class PsychAttemptDetail(BaseModel):
    id: uuid.UUID
    sitter_id: uuid.UUID
    sitter_name: str
    status: PsychAttemptStatus
    submitted_at: datetime | None
    reviewed_at: datetime | None
    notes: str | None
    answers: list[PsychAttemptAnswerOut]


@router.get("/psych-attempts/{attempt_id}")
def get_psych_attempt(attempt_id: uuid.UUID, admin: Admin, db: DbSession) -> PsychAttemptDetail:
    attempt = psych_tests_service.get_attempt(db, attempt_id)
    questions = psych_tests_service.list_questions(db, attempt.test_id)
    answers = psych_tests_service.list_answers(db, attempt.id)
    name = _sitter_names(db, [attempt.sitter_id]).get(attempt.sitter_id, "")
    return PsychAttemptDetail(
        id=attempt.id,
        sitter_id=attempt.sitter_id,
        sitter_name=name,
        status=attempt.status,
        submitted_at=attempt.submitted_at,
        reviewed_at=attempt.reviewed_at,
        notes=attempt.notes,
        answers=[
            PsychAttemptAnswerOut(
                question_id=question.id,
                kind=question.kind,
                prompt=question.prompt,
                options=question.options,
                answer_text=answers.get(question.id),
            )
            for question in questions
        ],
    )


class PsychAttemptDecisionIn(BaseModel):
    passed: bool
    notes: str | None = Field(default=None, max_length=2000)


class PsychAttemptDecisionOut(BaseModel):
    id: uuid.UUID
    status: PsychAttemptStatus


@router.post("/psych-attempts/{attempt_id}/decision")
def decide_psych_attempt(
    attempt_id: uuid.UUID, body: PsychAttemptDecisionIn, admin: Admin, db: DbSession
) -> PsychAttemptDecisionOut:
    attempt = psych_tests_service.record_decision(db, admin.id, attempt_id, body.passed, body.notes)
    return PsychAttemptDecisionOut(id=attempt.id, status=attempt.status)
