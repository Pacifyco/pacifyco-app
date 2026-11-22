"""The admin area. Every route here is for admins only (CLAUDE.md 9: wrong role gets 403)."""

import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from app.auth import require_role
from app.deps import DbSession
from app.errors import AppError
from app.models import (
    Booking,
    BookingStatus,
    ComplaintStatus,
    DocumentType,
    OnboardingStatus,
    OnboardingStepName,
    OvertimeCharge,
    Payment,
    PaymentKind,
    PaymentStatus,
    PayoutMethod,
    Profile,
    ProfileStatus,
    PsychAttemptStatus,
    PsychQuestionKind,
    Role,
    SitterLevel,
    StrikeReason,
    VerificationStatus,
)
from app.routers.sitters import StrikeOut, strikes_out
from app.services import booking_mail, documents, verification
from app.services import bookings as bookings_service
from app.services import chat as chat_service
from app.services import checkin as checkin_service
from app.services import children as children_service
from app.services import email as email_service
from app.services import incidents as incidents_service
from app.services import payments as payments_service
from app.services import psych_tests as psych_tests_service
from app.services import reports as reports_service
from app.services import strikes as strikes_service
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
    decided = verification.decide_child(
        db, storage, admin.id, child_id, body.approved, body.notes, body.rejection_reason
    )
    child = decided.child
    profile, parent = verification.get_parent(db, child.parent_id)
    if decided.after is not None:  # paid bookings that lost their time, and others it took
        for lost_id in decided.after.lost:
            _tell_slot_taken(db, mailer, settings, _booking(db, lost_id), paid=True)
        for cancelled_id in decided.after.cancelled:
            _tell_cancelled_for(db, mailer, settings, cancelled_id)
    for request_id in decided.shown:  # requests the sitter can now see
        booking_mail.tell_sitter(db, mailer, settings, request_id)
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
    kind: PaymentKind  # booking, or a charge (cancellation_charge; overtime in phase 8)
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
                kind=payment.kind,
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
                note=payments_service.booking_note(booking.id)
                if payment.kind == PaymentKind.booking
                else payments_service.charge_note(payment.id),
                sent_at=payment.created_at
                if payment.kind == PaymentKind.booking
                else payments_service.reference_sent_at(db, payment) or payment.created_at,
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


def _booking(db: DbSession, booking_id: uuid.UUID) -> Booking:
    booking = db.get(Booking, booking_id)
    assert booking is not None
    return booking


def _tell_cancelled_for(db: DbSession, mailer: Mailer, settings: Settings, booking_id: uuid.UUID) -> None:
    """Another booking was confirmed for this one's time."""
    sent = payments_service.latest_booking_payment(db, booking_id)
    _tell_slot_taken(db, mailer, settings, _booking(db, booking_id), paid=sent is not None)


def _charge_decided(db: DbSession, mailer: Mailer, settings: Settings, charge: Payment, rejected: str | None):
    booking = db.get(Booking, charge.booking_id)
    assert booking is not None
    parent, _ = _people(db, booking)
    if rejected is None:
        mailer.send(
            email_service.charge_paid(
                parent.email, parent.full_name, charge.amount_paise, charge.id, _web_url(settings)
            )
        )
    else:
        mailer.send(
            email_service.charge_reference_rejected(
                parent.email, parent.full_name, rejected, charge.id, _web_url(settings)
            )
        )
    return PaymentDecisionOut(
        status=PaymentStatus.confirmed if rejected is None else PaymentStatus.rejected,
        booking_status=booking.status,
        refund_owed=False,
        cancelled_bookings=0,
    )


@router.post("/payments/{payment_id}/confirm")
def confirm_payment(
    payment_id: uuid.UUID, admin: Admin, db: DbSession, mailer: Mailer, settings: AppSettings
) -> PaymentDecisionOut:
    charge = payments_service.sent_charge(db, payment_id)
    if charge is not None:  # a charge the parent has paid (6.5, 6.8): no longer owed
        payments_service.confirm_charge(db, admin.id, charge, datetime.now(UTC))
        return _charge_decided(db, mailer, settings, charge, None)
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
        _tell_cancelled_for(db, mailer, settings, cancelled_id)
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
    charge = payments_service.sent_charge(db, payment_id)
    if charge is not None:  # the reference is cleared; the charge is still owed
        payments_service.reject_charge_reference(db, admin.id, charge, body.reason)
        return _charge_decided(db, mailer, settings, charge, body.reason)
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


# ---------- strikes (CLAUDE.md 6.6) ----------


class AdminStrike(StrikeOut):
    removed_by: uuid.UUID | None
    doctor_note_document_id: uuid.UUID | None  # view it with /admin/documents/{id}/view-url (logged)


class AdminStrikes(BaseModel):
    blocked_until: datetime | None
    counting: int
    strikes: list[AdminStrike]


def _admin_strikes(db: DbSession, sitter_id: uuid.UUID) -> AdminStrikes:
    mine = strikes_out(db, sitter_id)
    found = {strike.id: strike for strike in strikes_service.for_sitter(db, sitter_id)}
    return AdminStrikes(
        blocked_until=mine.blocked_until,
        counting=mine.counting,
        strikes=[
            AdminStrike(
                **item.model_dump(),
                removed_by=found[item.id].removed_by,
                doctor_note_document_id=found[item.id].doctor_note_document_id,
            )
            for item in mine.strikes
        ],
    )


@router.get("/sitters/{sitter_id}/strikes")
def get_strikes(sitter_id: uuid.UUID, admin: Admin, db: DbSession) -> AdminStrikes:
    verification.get_sitter(db, sitter_id)
    return _admin_strikes(db, sitter_id)


class StrikeReasonIn(BaseModel):
    # Shown to the sitter.
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _not_blank(self) -> StrikeReasonIn:
        cleaned = _clean_reason(self.reason)
        if cleaned is None:
            raise ValueError("Please give a reason; it's shown to the sitter")
        self.reason = cleaned
        return self


@router.post("/sitters/{sitter_id}/strikes", status_code=201)
def add_strike(
    sitter_id: uuid.UUID, body: StrikeReasonIn, admin: Admin, db: DbSession, mailer: Mailer, settings: AppSettings
) -> AdminStrikes:
    """An admin gives a strike with a reason (6.6). It blocks her like any other; a 5th removes her."""
    profile, _ = verification.get_sitter(db, sitter_id)
    done = strikes_service.give(db, admin.id, sitter_id, StrikeReason.admin, datetime.now(UTC), note=body.reason)
    db.commit()
    mailer.send(
        email_service.strike_given(
            profile.email, profile.full_name, body.reason, done.blocked_until, _web_url(settings)
        )
    )
    if done.removed:
        booking_mail.tell_removed_for_strikes(db, mailer, settings, sitter_id)
    return _admin_strikes(db, sitter_id)


@router.post("/strikes/{strike_id}/remove")
def remove_strike(
    strike_id: uuid.UUID, body: StrikeReasonIn, admin: Admin, db: DbSession, mailer: Mailer, settings: AppSettings
) -> AdminStrikes:
    """An admin removes a strike with a reason, for example after a doctor's note (6.5, 6.6)."""
    done = strikes_service.remove(db, admin.id, strike_id, body.reason, datetime.now(UTC))
    profile = db.get(Profile, done.strike.sitter_id)
    assert profile is not None
    mailer.send(email_service.strike_removed(profile.email, profile.full_name, body.reason, _web_url(settings)))
    return _admin_strikes(db, done.strike.sitter_id)


# ---------- reports during a booking (CLAUDE.md 6.5) ----------


class AdminReport(BaseModel):
    """A report to act on: phone both people, then confirm or dismiss."""

    id: uuid.UUID
    kind: str  # parent_absent | sitter_no_show | only_man_home | child_under_age | sitter_unsafe
    reported_at: datetime
    responded_at: datetime | None
    can_leave_at: datetime | None
    booking_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    hours: int
    parent_name: str | None
    parent_phone: str | None
    sitter_name: str | None
    sitter_phone: str | None
    show_up_fee_paise: int  # what she's due if confirmed: show-up fee, ₹100, or her pay for 1 hour (under age)


def _admin_report(db: DbSession, report) -> AdminReport:
    booking = db.get(Booking, report.booking_id)
    assert booking is not None
    parent, sitter = _people(db, booking)
    return AdminReport(
        id=report.id,
        kind=report.kind.value,
        reported_at=report.reported_at,
        responded_at=report.responded_at,
        can_leave_at=reports_service.can_leave_at(report),
        booking_id=booking.id,
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
        hours=booking.units,
        parent_name=parent.full_name,
        parent_phone=parent.phone,
        sitter_name=sitter.full_name if sitter else None,
        sitter_phone=sitter.phone if sitter else None,
        show_up_fee_paise=reports_service.fee_paise(report, booking),
    )


@router.get("/reports")
def get_reports(admin: Admin, db: DbSession) -> list[AdminReport]:
    """Open reports, oldest first."""
    return [_admin_report(db, report) for report in reports_service.open_reports(db)]


@router.post("/reports/{report_id}/answered")
def mark_answered(report_id: uuid.UUID, admin: Admin, db: DbSession) -> AdminReport:
    """A parent answered an admin's call: the sitter waits for them (6.5)."""
    return _admin_report(db, reports_service.parent_responded(db, admin.id, report_id, datetime.now(UTC)))


class ReportDecisionIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


@router.post("/reports/{report_id}/confirm")
def confirm_report(
    report_id: uuid.UUID, body: ReportDecisionIn, admin: Admin, db: DbSession, mailer: Mailer, settings: AppSettings
) -> AdminReport:
    done = reports_service.decide(db, admin.id, report_id, True, _clean_reason(body.note or ""), datetime.now(UTC))
    booking_mail.tell_decided(db, mailer, settings, done.report, reports_service.fee_paise(done.report, done.booking))
    if done.strike is not None and done.strike.removed:
        booking_mail.tell_removed_for_strikes(db, mailer, settings, done.booking.sitter_id)
    return _admin_report(db, done.report)


@router.post("/reports/{report_id}/dismiss")
def dismiss_report(
    report_id: uuid.UUID, body: ReportDecisionIn, admin: Admin, db: DbSession, mailer: Mailer, settings: AppSettings
) -> AdminReport:
    note = _clean_reason(body.note or "")
    if note is None:
        raise AppError(422, "reason_needed", "Please say why you're dismissing it.")
    done = reports_service.decide(db, admin.id, report_id, False, note, datetime.now(UTC))
    booking_mail.tell_decided(db, mailer, settings, done.report, reports_service.fee_paise(done.report, done.booking))
    return _admin_report(db, done.report)


# ---------- overdue check-outs and locked codes (CLAUDE.md 6.7) ----------


class NeedsAttentionOut(BaseModel):
    """A booking to call about: still checked in long past its end, or its codes are locked."""

    booking_id: uuid.UUID
    overdue: bool  # otherwise it's here because its codes are locked
    starts_at: datetime
    ends_at: datetime
    parent_name: str | None
    parent_phone: str | None
    sitter_name: str | None
    sitter_phone: str | None
    checked_in: bool  # if she never did, the admin may choose hours to pay her when closing it


@router.get("/overdue-checkouts")
def get_needing_attention(admin: Admin, db: DbSession) -> list[NeedsAttentionOut]:
    found = checkin_service.needing_attention(db, datetime.now(UTC))
    out = []
    for item in found:
        parent, sitter = _people(db, item.booking)
        out.append(
            NeedsAttentionOut(
                booking_id=item.booking.id,
                overdue=item.overdue,
                starts_at=item.booking.starts_at,
                ends_at=item.booking.ends_at,
                parent_name=parent.full_name,
                parent_phone=parent.phone,
                sitter_name=sitter.full_name if sitter else None,
                sitter_phone=sitter.phone if sitter else None,
                checked_in=item.booking.checked_in_at is not None,
            )
        )
    return out


class CloseBookingIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    # Not charged by default; the admin may charge whole hours of overtime (Reuben, 2026-11-21).
    overtime_hours: int | None = Field(default=None, ge=1, le=6)
    # Only if she never checked in: whole hours to pay her, none by default (Reuben, 2026-11-22).
    pay_hours: int | None = Field(default=None, ge=1, le=24)


@router.post("/bookings/{booking_id}/close")
def close_booking(
    booking_id: uuid.UUID, body: CloseBookingIn, admin: Admin, db: DbSession, mailer: Mailer, settings: AppSettings
) -> NeedsAttentionOut:
    """An admin closes a booking by hand after calling both people (6.7)."""
    reason = _clean_reason(body.reason or "")
    if reason is None:
        raise AppError(422, "reason_needed", "Please say why you're closing it.")
    booking = checkin_service.close_by_admin(
        db, admin.id, booking_id, reason, datetime.now(UTC), body.overtime_hours, body.pay_hours
    )
    if body.overtime_hours:
        charge = db.scalar(select(OvertimeCharge).where(OvertimeCharge.booking_id == booking.id))
        payment = db.scalar(
            select(Payment).where(
                Payment.booking_id == booking.id,
                Payment.kind == PaymentKind.overtime,
                Payment.status == PaymentStatus.pending,
            )
        )
        if charge is not None and payment is not None:
            booking_mail.tell_parent_overtime_charged(
                db,
                mailer,
                settings,
                booking.id,
                amount_paise=charge.amount_paise,
                hours=charge.hours_charged,
                payment_id=payment.id,
            )
    parent, sitter = _people(db, booking)
    return NeedsAttentionOut(
        booking_id=booking.id,
        overdue=False,
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
        parent_name=parent.full_name,
        parent_phone=parent.phone,
        sitter_name=sitter.full_name if sitter else None,
        sitter_phone=sitter.phone if sitter else None,
        checked_in=booking.checked_in_at is not None,
    )


# ---------- emergencies and issues (CLAUDE.md 6.9) ----------


class AdminIncident(BaseModel):
    id: uuid.UUID
    kind: str
    status: str  # open (needs acknowledging) | acknowledged
    note: str | None
    raised_by: str  # parent | sitter
    created_at: datetime
    suspended_sitter: bool
    sitter_status: str
    booking_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    parent_name: str | None
    parent_phone: str | None
    sitter_name: str | None
    sitter_phone: str | None


def _admin_incident(db: DbSession, incident) -> AdminIncident:
    booking = db.get(Booking, incident.booking_id)
    assert booking is not None
    parent, sitter = _people(db, booking)
    return AdminIncident(
        id=incident.id,
        kind=incident.kind.value,
        status=incident.status.value,
        note=incident.note,
        raised_by="parent" if incident.raised_by == parent.id else "sitter",
        created_at=incident.created_at,
        suspended_sitter=incident.suspended_sitter,
        sitter_status=sitter.status.value if sitter else "removed",
        booking_id=booking.id,
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
        parent_name=parent.full_name,
        parent_phone=parent.phone,
        sitter_name=sitter.full_name if sitter else None,
        sitter_phone=sitter.phone if sitter else None,
    )


@router.get("/incidents")
def get_incidents(admin: Admin, db: DbSession) -> list[AdminIncident]:
    """Unresolved emergencies, newest first. Open ones show at the top of the admin panel until acknowledged."""
    return [_admin_incident(db, incident) for incident in incidents_service.open_incidents(db)]


@router.post("/incidents/{incident_id}/acknowledge")
def acknowledge_incident(incident_id: uuid.UUID, admin: Admin, db: DbSession) -> AdminIncident:
    return _admin_incident(db, incidents_service.acknowledge(db, admin.id, incident_id, datetime.now(UTC)))


class ResolveIn(BaseModel):
    note: str = Field(min_length=1, max_length=1000)
    reinstate_sitter: bool = False  # only matters if the report suspended her


@router.post("/incidents/{incident_id}/resolve")
def resolve_incident(
    incident_id: uuid.UUID, body: ResolveIn, admin: Admin, db: DbSession, mailer: Mailer, settings: AppSettings
) -> AdminIncident:
    note = _clean_reason(body.note)
    if note is None:
        raise AppError(422, "note_needed", "Please say what happened.")
    incident = incidents_service.resolve(db, admin.id, incident_id, note, body.reinstate_sitter, datetime.now(UTC))
    booking = db.get(Booking, incident.booking_id)
    assert booking is not None
    _, sitter = _people(db, booking)
    if incident.suspended_sitter and sitter and sitter.status == ProfileStatus.active:
        mailer.send(email_service.sitter_reinstated(sitter.email, sitter.full_name, _web_url(settings)))
    return _admin_incident(db, incident)


class AdminIssue(BaseModel):
    id: uuid.UUID
    topic: str | None
    description: str
    status: str  # open | replied
    raised_by: str  # parent | sitter
    created_at: datetime
    booking_id: uuid.UUID | None
    starts_at: datetime | None
    parent_name: str | None
    parent_phone: str | None
    sitter_name: str | None
    sitter_phone: str | None


def _admin_issue(db: DbSession, complaint) -> AdminIssue:
    booking = db.get(Booking, complaint.booking_id) if complaint.booking_id else None
    parent, sitter = _people(db, booking) if booking else (None, None)
    return AdminIssue(
        id=complaint.id,
        topic=complaint.topic.value if complaint.topic else None,
        description=complaint.description,
        status=complaint.status.value,
        raised_by="parent" if parent and complaint.raised_by == parent.id else "sitter",
        created_at=complaint.created_at,
        booking_id=booking.id if booking else None,
        starts_at=booking.starts_at if booking else None,
        parent_name=parent.full_name if parent else None,
        parent_phone=parent.phone if parent else None,
        sitter_name=sitter.full_name if sitter else None,
        sitter_phone=sitter.phone if sitter else None,
    )


@router.get("/issues")
def get_issues(admin: Admin, db: DbSession) -> list[AdminIssue]:
    """Issues not yet resolved, oldest first."""
    return [_admin_issue(db, complaint) for complaint in incidents_service.open_issues(db)]


@router.post("/issues/{complaint_id}/replied")
def issue_replied(complaint_id: uuid.UUID, admin: Admin, db: DbSession) -> AdminIssue:
    done = incidents_service.update_issue(db, admin.id, complaint_id, ComplaintStatus.replied, datetime.now(UTC))
    return _admin_issue(db, done)


@router.post("/issues/{complaint_id}/resolved")
def issue_resolved(complaint_id: uuid.UUID, admin: Admin, db: DbSession) -> AdminIssue:
    done = incidents_service.update_issue(db, admin.id, complaint_id, ComplaintStatus.resolved, datetime.now(UTC))
    return _admin_issue(db, done)


class AdminMessage(BaseModel):
    sender: str  # parent | sitter
    body: str
    created_at: datetime


@router.get("/incidents/{incident_id}/chat")
def incident_chat(incident_id: uuid.UUID, admin: Admin, db: DbSession) -> list[AdminMessage]:
    """The chat between the incident's parent and sitter, for handling it (6.11). Every read is audit logged."""
    found = chat_service.read_for_incident(db, admin.id, incident_id)
    return [
        AdminMessage(
            sender="parent" if message.sender_id == message.parent_id else "sitter",
            body=message.body,
            created_at=message.created_at,
        )
        for message in found
    ]
