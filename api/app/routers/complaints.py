"""A parent's or sitter's own complaints and appeal (CLAUDE.md 6.12; phase 10).

Both roles use these, so they aren't under one role's area; each endpoint checks for itself (listed in
PUBLIC in tests/test_roles.py). Raising a complaint needs an active or pending account. A suspended or
removed account can still appeal, and read and write on its appeal, but nothing else.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth import BLOCKED_STATUSES, CurrentUser, current_profile, current_user
from app.deps import DbSession
from app.errors import AppError
from app.models import Complaint, ComplaintStatus, ComplaintType, Profile, Role
from app.services import complaint_mail, complaints
from app.services import email as email_service
from app.settings import Settings, get_settings

router = APIRouter(prefix="/me", tags=["complaints"])
AppSettings = Annotated[Settings, Depends(get_settings)]
Mailer = Annotated[email_service.EmailClient, Depends(email_service.get_email)]
PEOPLE = (Role.parent, Role.sitter)


def any_status(user: Annotated[CurrentUser, Depends(current_user)]) -> Profile:
    """A parent or sitter, suspended or removed ones too (for their appeal)."""
    if user.profile is None:
        raise AppError(403, "profile_required", "Please finish joining Pacifyco first")
    if user.profile.role not in PEOPLE:
        raise AppError(403, "forbidden", "This isn't available for your account")
    return user.profile


def active(profile: Annotated[Profile, Depends(current_profile)]) -> Profile:
    """A parent or sitter whose account isn't suspended or removed."""
    if profile.role not in PEOPLE:
        raise AppError(403, "forbidden", "This isn't available for your account")
    return profile


Person = Annotated[Profile, Depends(any_status)]
ActivePerson = Annotated[Profile, Depends(active)]


class MessageOut(BaseModel):
    id: uuid.UUID
    from_pacifyco: bool
    body: str
    at: datetime


class AttachmentOut(BaseModel):
    id: uuid.UUID
    uploaded_at: datetime


class ComplaintRow(BaseModel):
    id: uuid.UUID
    type: str
    status: str
    description: str
    created_at: datetime


class ComplaintOut(ComplaintRow):
    booking_id: uuid.UUID | None
    happened_on: date | None
    late: bool
    reply_by: datetime
    resolve_by: datetime
    first_reply_at: datetime | None
    resolved_at: datetime | None
    resolution: str | None
    appeal_outcome: str | None
    escalated_at: datetime | None
    officer_acknowledged_at: datetime | None
    officer_decision: str | None
    officer_decided_at: datetime | None
    can_write: bool
    can_escalate: bool
    can_attach: bool
    messages: list[MessageOut]
    attachments: list[AttachmentOut]


def _row(complaint: Complaint) -> ComplaintRow:
    return ComplaintRow(
        id=complaint.id,
        type=complaint.type.value,
        status=complaint.status.value,
        description=complaint.description,
        created_at=complaint.created_at,
    )


def complaint_out(db: DbSession, person: Profile, complaint: Complaint) -> ComplaintOut:
    files = complaints.attachments(db, complaint.id)
    return ComplaintOut(
        **_row(complaint).model_dump(),
        booking_id=complaint.booking_id,
        happened_on=complaint.happened_on,
        late=complaint.late,
        reply_by=complaint.reply_by,
        resolve_by=complaint.resolve_by,
        first_reply_at=complaint.first_reply_at,
        resolved_at=complaint.resolved_at,
        resolution=complaint.resolution,
        appeal_outcome=complaint.appeal_outcome.value if complaint.appeal_outcome else None,
        escalated_at=complaint.escalated_at,
        officer_acknowledged_at=complaint.officer_acknowledged_at,
        officer_decision=complaint.officer_decision,
        officer_decided_at=complaint.officer_decided_at,
        can_write=complaint.status != ComplaintStatus.closed,
        can_escalate=complaint.status == ComplaintStatus.resolved,
        can_attach=complaint.type != ComplaintType.suspension
        and complaint.status != ComplaintStatus.closed
        and len(files) < complaints.ATTACHMENTS_MAX,
        messages=[
            MessageOut(id=item.id, from_pacifyco=item.author_id != person.id, body=item.body, at=item.created_at)
            for item in complaints.messages(db, complaint.id)
        ],
        attachments=[AttachmentOut(id=item.id, uploaded_at=item.created_at) for item in files],
    )


class ComplaintIn(BaseModel):
    type: ComplaintType
    description: str = Field(max_length=complaints.TEXT_MAX)
    booking_id: uuid.UUID | None = None
    happened_on: date | None = None  # India date; not asked for a booking (its end is used)


class TextIn(BaseModel):
    body: str = Field(max_length=complaints.TEXT_MAX)


@router.get("/complaints")
def my_complaints(person: Person, db: DbSession) -> list[ComplaintRow]:
    """Theirs, newest first. A suspended or removed account sees only its appeal."""
    found = complaints.mine(db, person.id)
    if person.status in BLOCKED_STATUSES:
        found = [item for item in found if item.type == ComplaintType.suspension]
    return [_row(item) for item in found]


@router.post("/complaints", status_code=201)
def raise_complaint(
    body: ComplaintIn, person: ActivePerson, db: DbSession, settings: AppSettings, mailer: Mailer
) -> ComplaintOut:
    complaint = complaints.raise_complaint(
        db, person, body.type, body.description, body.booking_id, body.happened_on, datetime.now(UTC)
    )
    complaint_mail.tell_raised(db, mailer, settings, complaint)
    return complaint_out(db, person, complaint)


@router.get("/complaints/{complaint_id}")
def my_complaint(complaint_id: uuid.UUID, person: Person, db: DbSession) -> ComplaintOut:
    return complaint_out(db, person, complaints.persons(db, person, complaint_id))


@router.post("/complaints/{complaint_id}/messages")
def write(
    complaint_id: uuid.UUID, body: TextIn, person: Person, db: DbSession, settings: AppSettings, mailer: Mailer
) -> ComplaintOut:
    complaint = complaints.person_writes(db, person, complaint_id, body.body, datetime.now(UTC))
    complaint_mail.tell_person_wrote(mailer, settings, complaint)
    return complaint_out(db, person, complaint)


@router.post("/complaints/{complaint_id}/escalate")
def escalate(
    complaint_id: uuid.UUID, body: TextIn, person: Person, db: DbSession, settings: AppSettings, mailer: Mailer
) -> ComplaintOut:
    """They disagree with how it was resolved: it goes to the Grievance Officer."""
    complaint = complaints.person_escalates(db, person, complaint_id, body.body, datetime.now(UTC))
    complaint_mail.tell_escalated(db, mailer, settings, [complaint], overdue=False)
    return complaint_out(db, person, complaint)


class DecisionOut(BaseModel):
    action: str  # suspended | removed
    reason: str
    at: datetime


class AppealOut(BaseModel):
    decision: DecisionOut | None  # None: nothing to appeal
    appeal_by: datetime | None
    can_appeal: bool
    appeal: ComplaintOut | None


@router.get("/appeal")
def my_appeal(person: Person, db: DbSession) -> AppealOut:
    """For a suspended or removed account: the decision, until when it can be appealed, and the appeal."""
    state = complaints.appeal_state(db, person)
    now = datetime.now(UTC)
    return AppealOut(
        decision=DecisionOut(
            action=state.decision.action.value, reason=state.decision.reason, at=state.decision.created_at
        )
        if state.decision
        else None,
        appeal_by=state.appeal_by,
        can_appeal=state.decision is not None and state.appeal is None and now <= state.appeal_by,
        appeal=complaint_out(db, person, state.appeal) if state.appeal else None,
    )


@router.post("/appeal", status_code=201)
def send_appeal(body: TextIn, person: Person, db: DbSession, settings: AppSettings, mailer: Mailer) -> AppealOut:
    complaint = complaints.appeal(db, person, body.body, datetime.now(UTC))
    complaint_mail.tell_raised(db, mailer, settings, complaint)
    return my_appeal(person, db)
