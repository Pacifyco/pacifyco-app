"""The admin area. Every route here is for admins only (CLAUDE.md 9: wrong role gets 403)."""

import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from app.auth import require_role
from app.deps import DbSession
from app.models import (
    Booking,
    BookingStatus,
    DocumentType,
    OnboardingStatus,
    OnboardingStepName,
    Payment,
    PaymentStatus,
    PayoutMethod,
    Profile,
    ProfileStatus,
    PsychAttemptStatus,
    PsychQuestionKind,
    Role,
    SitterLevel,
    VerificationStatus,
)
from app.services import bookings as bookings_service
from app.services import children as children_service
from app.services import documents, verification
from app.services import email as email_service
from app.services import payments as payments_service
from app.services import psych_tests as psych_tests_service
from app.services.storage import StorageClient, get_storage
from app.settings import LOCAL_WEB_ORIGIN, Settings, get_settings

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role(Role.admin))])
Admin = Annotated[Profile, Depends(require_role(Role.admin))]
Storage = Annotated[StorageClient, Depends(get_storage)]
AppSettings = Annotated[Settings, Depends(get_settings)]
Mailer = Annotated[email_service.EmailClient, Depends(email_service.get_email)]


def _web_url(settings: Settings) -> str:
    return settings.public_web_url or LOCAL_WEB_ORIGIN


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
    rows = db.execute(select(Profile.id, Profile.full_name, Profile.email).where(Profile.id.in_(sitter_ids)))
    return {row.id: row.full_name or row.email for row in rows}  # the name is filled in after sign-up


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
    rejection_reason: str | None
    retake_allowed: bool
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
        rejection_reason=attempt.rejection_reason,
        retake_allowed=attempt.retake_allowed_at is not None,
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


def _clean_reason(value: str | None) -> str | None:
    return (value.strip() or None) if value is not None else None


class PsychAttemptDecisionIn(BaseModel):
    passed: bool
    notes: str | None = Field(default=None, max_length=2000)
    # Shown to the parent or sitter (decided 2026-11-09). Required when rejecting; notes stay internal.
    rejection_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _reason_when_failing(self) -> PsychAttemptDecisionIn:
        self.rejection_reason = _clean_reason(self.rejection_reason)
        if not self.passed and self.rejection_reason is None:
            raise ValueError("Please give a reason for failing; it's shown to her")
        return self


class PsychAttemptDecisionOut(BaseModel):
    id: uuid.UUID
    status: PsychAttemptStatus


@router.post("/psych-attempts/{attempt_id}/decision")
def decide_psych_attempt(
    attempt_id: uuid.UUID,
    body: PsychAttemptDecisionIn,
    admin: Admin,
    db: DbSession,
    mailer: Mailer,
    settings: AppSettings,
) -> PsychAttemptDecisionOut:
    attempt = psych_tests_service.record_decision(
        db, admin.id, attempt_id, body.passed, body.notes, body.rejection_reason
    )
    if not body.passed:  # rejection emails (Reuben, 2026-11-13)
        profile = db.get(Profile, attempt.sitter_id)
        if profile is not None:
            mailer.send(
                email_service.psych_test_failed(
                    profile.email, profile.full_name, attempt.rejection_reason, _web_url(settings)
                )
            )
    return PsychAttemptDecisionOut(id=attempt.id, status=attempt.status)


@router.post("/psych-attempts/{attempt_id}/allow-retake")
def allow_psych_retake(attempt_id: uuid.UUID, admin: Admin, db: DbSession) -> PsychAttemptDecisionOut:
    """After a fail, let her take the screening again (decided 2026-11-08)."""
    attempt = psych_tests_service.allow_retake(db, admin.id, attempt_id)
    return PsychAttemptDecisionOut(id=attempt.id, status=attempt.status)


# ---------- verification queue (CLAUDE.md 7) ----------


class Decision(BaseModel):
    approved: bool
    notes: str | None = Field(default=None, max_length=2000)
    # Shown to the parent or sitter (decided 2026-11-09). Required when rejecting; notes stay internal.
    rejection_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _reason_when_rejecting(self) -> Decision:
        self.rejection_reason = _clean_reason(self.rejection_reason)
        if not self.approved and self.rejection_reason is None:
            raise ValueError("Please give a reason for rejecting; it's shown to them")
        return self


class SitterQueueItem(BaseModel):
    id: uuid.UUID
    full_name: str | None  # filled in after sign-up (CLAUDE.md 6.13)
    email: str
    signed_up_at: datetime
    steps_approved: int
    steps_total: int
    level: SitterLevel | None


class FamilyQueueItem(BaseModel):
    id: uuid.UUID
    full_name: str | None  # filled in after sign-up (CLAUDE.md 6.13)
    email: str
    signed_up_at: datetime
    children_to_review: int


class VerificationQueue(BaseModel):
    sitters: list[SitterQueueItem]
    families: list[FamilyQueueItem]


@router.get("/verifications")
def verification_queue(admin: Admin, db: DbSession) -> VerificationQueue:
    return VerificationQueue(
        sitters=[
            SitterQueueItem(
                id=item.profile.id,
                full_name=item.profile.full_name,
                email=item.profile.email,
                signed_up_at=item.profile.created_at,
                steps_approved=item.steps_approved,
                steps_total=len(verification.REVIEWED_STEPS),
                level=item.sitter.level,
            )
            for item in verification.sitters_to_review(db)
        ],
        families=[
            FamilyQueueItem(
                id=item.profile.id,
                full_name=item.profile.full_name,
                email=item.profile.email,
                signed_up_at=item.profile.created_at,
                children_to_review=item.children_to_review,
            )
            for item in verification.families_to_review(db)
        ],
    )


class DocumentSummary(BaseModel):
    id: uuid.UUID
    type: DocumentType
    uploaded_at: datetime


class ReferenceOut(BaseModel):
    id: uuid.UUID
    name: str
    phone: str
    relationship: str
    outcome: VerificationStatus
    notes: str | None
    rejection_reason: str | None


class PsychAttemptRef(BaseModel):
    id: uuid.UUID
    status: PsychAttemptStatus
    submitted_at: datetime | None


class SitterReview(BaseModel):
    """Everything an admin needs to review a sitter, except health data and payout details: the
    health disclosure has its own logged endpoint, and payout details aren't part of vetting."""

    id: uuid.UUID
    full_name: str | None  # filled in after sign-up (CLAUDE.md 6.13)
    email: str
    phone: str | None
    pin_code: str | None
    profile_status: ProfileStatus
    signed_up_at: datetime
    date_of_birth: date | None
    bio: str | None
    years_experience: int | None
    university: str | None
    semester: int | None
    age_groups: list[str]
    languages: list[str]
    first_aid: bool
    reference_shared_consent: bool
    has_health_disclosure: bool
    payout_method: PayoutMethod | None
    onboarding_status: OnboardingStatus
    level: SitterLevel | None
    steps: dict[str, VerificationStatus]
    documents: list[DocumentSummary]
    references: list[ReferenceOut]
    psych_attempt: PsychAttemptRef | None


@router.get("/sitters/{sitter_id}")
def get_sitter_review(sitter_id: uuid.UUID, admin: Admin, db: DbSession) -> SitterReview:
    profile, sitter = verification.get_sitter(db, sitter_id)
    attempt = psych_tests_service.latest_attempt(db, sitter_id)
    return SitterReview(
        id=profile.id,
        full_name=profile.full_name,
        email=profile.email,
        phone=profile.phone,
        pin_code=profile.pin_code,
        profile_status=profile.status,
        signed_up_at=profile.created_at,
        date_of_birth=sitter.date_of_birth,
        bio=sitter.bio,
        years_experience=sitter.years_experience,
        university=sitter.university,
        semester=sitter.semester,
        age_groups=sitter.age_groups,
        languages=sitter.languages,
        first_aid=sitter.first_aid,
        reference_shared_consent=sitter.reference_shared_consent,
        has_health_disclosure=sitter.health_disclosure_encrypted is not None,
        payout_method=sitter.payout_method,
        onboarding_status=sitter.onboarding_status,
        level=sitter.level,
        steps=verification.step_statuses(db, sitter_id),
        documents=[
            DocumentSummary(id=doc.id, type=doc.type, uploaded_at=doc.created_at)
            for doc in verification.sitter_documents(db, sitter_id)
        ],
        references=[
            ReferenceOut(
                id=ref.id,
                name=ref.name,
                phone=ref.phone,
                relationship=ref.relationship,
                outcome=ref.outcome,
                notes=ref.notes,
                rejection_reason=ref.rejection_reason,
            )
            for ref in verification.sitter_references(db, sitter_id)
        ],
        psych_attempt=(
            PsychAttemptRef(id=attempt.id, status=attempt.status, submitted_at=attempt.submitted_at)
            if attempt is not None
            else None
        ),
    )


class HealthDisclosureOut(BaseModel):
    disclosure: str | None


@router.get("/sitters/{sitter_id}/health-disclosure")
def view_health_disclosure(
    sitter_id: uuid.UUID, admin: Admin, db: DbSession, settings: AppSettings
) -> HealthDisclosureOut:
    """Health data: every view is logged (CLAUDE.md 7 step 1)."""
    return HealthDisclosureOut(
        disclosure=verification.view_health_disclosure(db, admin.id, sitter_id, settings.field_encryption_key)
    )


class StatusOut(BaseModel):
    status: VerificationStatus


@router.post("/sitters/{sitter_id}/steps/{step}")
def review_onboarding_step(
    sitter_id: uuid.UUID,
    step: OnboardingStepName,
    body: Decision,
    admin: Admin,
    db: DbSession,
    mailer: Mailer,
    settings: AppSettings,
) -> StatusOut:
    row = verification.record_step(db, admin.id, sitter_id, step, body.approved, body.notes, body.rejection_reason)
    if not body.approved:
        profile, _ = verification.get_sitter(db, sitter_id)
        mailer.send(
            email_service.sitter_step_rejected(
                profile.email, profile.full_name, step.value, body.rejection_reason, _web_url(settings)
            )
        )
    return StatusOut(status=row.status)


@router.post("/references/{reference_id}/decision")
def review_reference(
    reference_id: uuid.UUID, body: Decision, admin: Admin, db: DbSession, mailer: Mailer, settings: AppSettings
) -> StatusOut:
    reference = verification.record_reference_outcome(
        db, admin.id, reference_id, body.approved, body.notes, body.rejection_reason
    )
    if not body.approved:
        profile, _ = verification.get_sitter(db, reference.sitter_id)
        mailer.send(
            email_service.reference_rejected(
                profile.email, profile.full_name, reference.name, body.rejection_reason, _web_url(settings)
            )
        )
    return StatusOut(status=reference.outcome)


class LevelIn(BaseModel):
    level: SitterLevel


@router.put("/sitters/{sitter_id}/level")
def set_sitter_level(sitter_id: uuid.UUID, body: LevelIn, admin: Admin, db: DbSession) -> LevelIn:
    verification.set_level(db, admin.id, sitter_id, body.level)
    return LevelIn(level=body.level)


class OnboardingStatusOut(BaseModel):
    onboarding_status: OnboardingStatus


@router.post("/sitters/{sitter_id}/decision")
def decide_sitter(
    sitter_id: uuid.UUID, body: Decision, admin: Admin, db: DbSession, mailer: Mailer, settings: AppSettings
) -> OnboardingStatusOut:
    sitter = verification.decide_sitter(db, admin.id, sitter_id, body.approved, body.notes, body.rejection_reason)
    profile, _ = verification.get_sitter(db, sitter_id)
    if body.approved:  # she hears that she's live (approval emails brought forward, 2026-11-13)
        mailer.send(email_service.sitter_approved(profile.email, profile.full_name, _web_url(settings)))
    else:  # and why, if not (rejection emails, 2026-11-13)
        mailer.send(
            email_service.sitter_application_rejected(
                profile.email, profile.full_name, body.rejection_reason, _web_url(settings)
            )
        )
    return OnboardingStatusOut(onboarding_status=sitter.onboarding_status)


class ChildReview(BaseModel):
    id: uuid.UUID
    name: str
    date_of_birth: date
    verification_status: VerificationStatus
    verified_at: datetime | None
    verification_notes: str | None
    rejection_reason: str | None
    birth_certificates: list[DocumentSummary]


class FamilyReview(BaseModel):
    id: uuid.UUID
    full_name: str | None  # filled in after sign-up (CLAUDE.md 6.13)
    email: str
    phone: str | None
    pin_code: str | None
    profile_status: ProfileStatus
    verification_status: VerificationStatus
    signed_up_at: datetime
    children: list[ChildReview]


@router.get("/parents/{parent_id}")
def get_family_review(parent_id: uuid.UUID, admin: Admin, db: DbSession) -> FamilyReview:
    profile, parent = verification.get_parent(db, parent_id)
    return FamilyReview(
        id=profile.id,
        full_name=profile.full_name,
        email=profile.email,
        phone=profile.phone,
        pin_code=profile.pin_code,
        profile_status=profile.status,
        verification_status=parent.verification_status,
        signed_up_at=profile.created_at,
        children=[
            ChildReview(
                id=child.id,
                name=child.name,
                date_of_birth=child.date_of_birth,
                verification_status=child.verification_status,
                verified_at=child.verified_at,
                verification_notes=child.verification_notes,
                rejection_reason=child.rejection_reason,
                birth_certificates=[
                    DocumentSummary(id=doc.id, type=doc.type, uploaded_at=doc.created_at)
                    for doc in verification.birth_certificates(db, child.id)
                ],
            )
            for child in children_service.list_children(db, parent_id)
        ],
    )


@router.post("/children/{child_id}/decision")
def decide_child(
    child_id: uuid.UUID,
    body: Decision,
    admin: Admin,
    db: DbSession,
    storage: Storage,
    mailer: Mailer,
    settings: AppSettings,
) -> StatusOut:
    child = verification.decide_child(db, storage, admin.id, child_id, body.approved, body.notes, body.rejection_reason)
    profile, parent = verification.get_parent(db, child.parent_id)
    if body.approved:  # the parent hears their child is verified (brought forward, 2026-11-13)
        family_verified = parent.verification_status == VerificationStatus.approved
        mailer.send(
            email_service.child_verified(
                profile.email, profile.full_name, child.name, family_verified, _web_url(settings)
            )
        )
    else:  # and why the certificate couldn't be accepted (rejection emails, 2026-11-13)
        mailer.send(
            email_service.child_rejected(
                profile.email, profile.full_name, child.name, child.rejection_reason, _web_url(settings)
            )
        )
    return StatusOut(status=child.verification_status)


# ---------- booking payments and refunds (CLAUDE.md 6.1; phase 6) ----------


class PaymentToCheck(BaseModel):
    """A UPI payment a parent says they've made: find the reference in Pacifyco's account, then confirm
    or reject it. Admins see the plan (parents never do)."""

    id: uuid.UUID
    booking_id: uuid.UUID
    parent_id: uuid.UUID
    parent_name: str | None
    parent_email: str
    sitter_name: str | None
    plan: SitterLevel
    starts_at: datetime
    hours: int
    amount_paise: int
    upi_reference: str | None
    note: str  # the note in the UPI link, to match the payment
    sent_at: datetime
    pay_by: datetime
    booking_status: BookingStatus
    children_verified: bool


class RefundToPay(BaseModel):
    """Money to pay back to a parent. Pay it to the account it came from (find it by the reference it
    was paid with), then record the transfer's reference."""

    id: uuid.UUID
    booking_id: uuid.UUID
    parent_id: uuid.UUID
    parent_name: str | None
    parent_email: str
    amount_paise: int  # positive: what to pay back
    paid_with_reference: str | None
    owed_since: datetime
    booking_status: BookingStatus


class PaymentsQueue(BaseModel):
    to_check: list[PaymentToCheck]
    refunds: list[RefundToPay]


def _people(db: DbSession, booking: Booking) -> tuple[Profile, Profile | None]:
    parent = db.get(Profile, booking.parent_id)
    assert parent is not None
    return parent, db.get(Profile, booking.sitter_id)


@router.get("/payments")
def payments_queue(admin: Admin, db: DbSession) -> PaymentsQueue:
    to_check, refunds = payments_service.waiting_for_admins(db)
    checks = []
    for payment in to_check:
        booking = db.get(Booking, payment.booking_id)
        assert booking is not None
        parent, sitter = _people(db, booking)
        checks.append(
            PaymentToCheck(
                id=payment.id,
                booking_id=booking.id,
                parent_id=parent.id,
                parent_name=parent.full_name,
                parent_email=parent.email,
                sitter_name=sitter.full_name if sitter else None,
                plan=booking.plan,
                starts_at=booking.starts_at,
                hours=booking.units,
                amount_paise=payment.amount_paise,
                upi_reference=payment.upi_reference,
                note=payments_service.booking_note(booking.id),
                sent_at=payment.created_at,
                pay_by=bookings_service.pay_by(booking),
                booking_status=booking.status,
                children_verified=bookings_service.children_verified(db, booking.id),
            )
        )
    owed = []
    for refund in refunds:
        booking = db.get(Booking, refund.booking_id)
        assert booking is not None
        parent, _ = _people(db, booking)
        paid_with = db.scalar(
            select(Payment.upi_reference)
            .where(Payment.booking_id == booking.id, Payment.status == PaymentStatus.confirmed)
            .where(Payment.upi_reference.is_not(None))
            .order_by(Payment.created_at.desc())
            .limit(1)
        )
        owed.append(
            RefundToPay(
                id=refund.id,
                booking_id=booking.id,
                parent_id=parent.id,
                parent_name=parent.full_name,
                parent_email=parent.email,
                amount_paise=-refund.amount_paise,
                paid_with_reference=paid_with,
                owed_since=refund.created_at,
                booking_status=booking.status,
            )
        )
    return PaymentsQueue(to_check=checks, refunds=owed)


class PaymentDecisionOut(BaseModel):
    status: PaymentStatus
    booking_status: BookingStatus
    refund_owed: bool
    # Other parents' unpaid bookings for that time, cancelled because this one was paid first.
    cancelled_bookings: int


def _tell_slot_taken(db: DbSession, mailer: Mailer, settings: Settings, booking: Booking, paid: bool) -> None:
    parent, sitter = _people(db, booking)
    mailer.send(
        email_service.booking_slot_taken(
            parent.email, parent.full_name, sitter.full_name if sitter else None, paid, booking.id, _web_url(settings)
        )
    )


@router.post("/payments/{payment_id}/confirm")
def confirm_payment(
    payment_id: uuid.UUID, admin: Admin, db: DbSession, mailer: Mailer, settings: AppSettings
) -> PaymentDecisionOut:
    done = payments_service.confirm(db, admin.id, payment_id, datetime.now(UTC))
    booking = done.booking
    if done.refund is not None:  # it lost her time to another booking
        _tell_slot_taken(db, mailer, settings, booking, paid=True)
    else:
        parent, sitter = _people(db, booking)
        mailer.send(
            email_service.booking_paid(
                parent.email,
                parent.full_name,
                sitter.full_name if sitter else None,
                booking.status == BookingStatus.confirmed,
                booking.id,
                _web_url(settings),
            )
        )
    for cancelled_id in done.cancelled:
        cancelled = db.get(Booking, cancelled_id)
        assert cancelled is not None
        sent = payments_service.latest_booking_payment(db, cancelled_id)
        _tell_slot_taken(db, mailer, settings, cancelled, paid=sent is not None)
    return PaymentDecisionOut(
        status=done.payment.status,
        booking_status=booking.status,
        refund_owed=done.refund is not None,
        cancelled_bookings=len(done.cancelled),
    )


class PaymentRejectionIn(BaseModel):
    # Shown to the parent, like every rejection reason (decided 2026-11-09).
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _not_blank(self) -> PaymentRejectionIn:
        cleaned = _clean_reason(self.reason)
        if cleaned is None:
            raise ValueError("Please give a reason for rejecting; it's shown to the parent")
        self.reason = cleaned
        return self


@router.post("/payments/{payment_id}/reject")
def reject_payment(
    payment_id: uuid.UUID,
    body: PaymentRejectionIn,
    admin: Admin,
    db: DbSession,
    mailer: Mailer,
    settings: AppSettings,
) -> PaymentDecisionOut:
    payment = payments_service.reject(db, admin.id, payment_id, body.reason, datetime.now(UTC))
    booking = db.get(Booking, payment.booking_id)
    assert booking is not None
    parent, _ = _people(db, booking)
    if booking.status == BookingStatus.pending_payment:  # still time to send the right reference
        mailer.send(
            email_service.booking_payment_rejected(
                parent.email, parent.full_name, body.reason, booking.id, _web_url(settings)
            )
        )
    return PaymentDecisionOut(
        status=payment.status, booking_status=booking.status, refund_owed=False, cancelled_bookings=0
    )


class RefundPaidIn(BaseModel):
    transfer_reference: str = Field(min_length=1, max_length=100)


class RefundOut(BaseModel):
    status: PaymentStatus
    transfer_reference: str | None


@router.post("/refunds/{refund_id}/paid")
def mark_refund_paid(
    refund_id: uuid.UUID,
    body: RefundPaidIn,
    admin: Admin,
    db: DbSession,
    mailer: Mailer,
    settings: AppSettings,
) -> RefundOut:
    refund = payments_service.mark_refunded(db, admin.id, refund_id, body.transfer_reference, datetime.now(UTC))
    booking = db.get(Booking, refund.booking_id)
    assert booking is not None
    parent, _ = _people(db, booking)
    mailer.send(
        email_service.refund_paid(parent.email, parent.full_name, -refund.amount_paise, booking.id, _web_url(settings))
    )
    return RefundOut(status=refund.status, transfer_reference=refund.transfer_reference)
