"""The admin area. Every route here is for admins only (CLAUDE.md 9: wrong role gets 403)."""

import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, or_, select

from app.auth import require_role
from app.deps import DbSession
from app.errors import AppError
from app.models import (
    AccountActionKind,
    AppealOutcome,
    AuditLog,
    Booking,
    BookingChild,
    BookingStatus,
    Child,
    Complaint,
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
    SitterEarning,
    SitterLevel,
    StrikeReason,
    VerificationStatus,
)
from app.routers.sitters import StrikeOut, strikes_out
from app.services import account_status as account_service
from app.services import admin_bookings as admin_bookings_service
from app.services import admin_logs as admin_logs_service
from app.services import booking_mail, complaint_mail, documents, verification
from app.services import bookings as bookings_service
from app.services import chat as chat_service
from app.services import checkin as checkin_service
from app.services import children as children_service
from app.services import complaints as complaints_service
from app.services import dashboard as dashboard_service
from app.services import email as email_service
from app.services import incidents as incidents_service
from app.services import payments as payments_service
from app.services import payouts as payouts_service
from app.services import psych_tests as psych_tests_service
from app.services import reports as reports_service
from app.services import reviews as reviews_service
from app.services import strikes as strikes_service
from app.services.availability import today_in_india
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
def allow_psych_retake(
    attempt_id: uuid.UUID, admin: Admin, db: DbSession, mailer: Mailer, settings: AppSettings
) -> PsychAttemptDecisionOut:
    """After a fail, let her take the screening again (decided 2026-11-08); she's emailed (phase 11)."""
    attempt = psych_tests_service.allow_retake(db, admin.id, attempt_id)
    sitter = db.get(Profile, attempt.sitter_id)
    if sitter is not None:
        mailer.send(email_service.psych_retake_allowed(sitter.email, sitter.full_name, _web_url(settings)))
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


class ReviewForAdmin(BaseModel):
    """A review, with the author's full name and the booking (6.11)."""

    id: uuid.UUID
    booking_id: uuid.UUID
    rating: int
    body: str | None
    author_name: str | None
    created_at: datetime


def _reviews_about(db, subject_id: uuid.UUID) -> list[ReviewForAdmin]:
    return [ReviewForAdmin(**vars(item)) for item in reviews_service.about(db, subject_id)]


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
    # Families' reviews of her (6.11)
    avg_rating: float | None
    review_count: int
    reviews: list[ReviewForAdmin]


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
        avg_rating=float(sitter.avg_rating) if sitter.avg_rating is not None else None,
        review_count=sitter.review_count,
        reviews=_reviews_about(db, sitter_id),
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
    # Sitters' reviews of the family: only admins see them (Reuben, 2026-11-22).
    reviews: list[ReviewForAdmin]


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
        reviews=_reviews_about(db, parent_id),
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
        if booking.status == BookingStatus.confirmed and sitter is not None:
            booking_mail.tell_sitter_confirmed(db, mailer, settings, booking.id)
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


# ---------- emergencies (CLAUDE.md 6.9) ----------


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


# ---------- payouts due (CLAUDE.md 6.10; phase 9) ----------


class BankOut(BaseModel):
    account_holder_name: str
    account_number: str
    ifsc_code: str


class DueEarningOut(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    booking_starts_at: datetime
    kind: str  # booking | overtime | show_up_fee
    amount_paise: int
    minutes: int | None
    due_by: datetime


class SitterDueOut(BaseModel):
    """Everything due to one sitter: one transfer (Reuben, 2026-11-22)."""

    sitter_id: uuid.UUID
    sitter_name: str | None
    sitter_phone: str | None
    payout_method: str | None  # bank | upi
    upi_id: str | None
    bank: BankOut | None  # shown, so an audit row is written (Reuben, 2026-11-22)
    total_paise: int
    next_due_by: datetime
    earnings: list[DueEarningOut]


@router.get("/payouts")
def payouts_due(admin: Admin, db: DbSession, settings: AppSettings) -> list[SitterDueOut]:
    """Released, unpaid earnings by sitter, soonest deadline first."""
    found = payouts_service.due(db, admin.id, settings.field_encryption_key)
    return [
        SitterDueOut(
            sitter_id=group.sitter.profile_id,
            sitter_name=group.profile.full_name,
            sitter_phone=group.profile.phone,
            payout_method=group.sitter.payout_method.value if group.sitter.payout_method else None,
            upi_id=group.sitter.upi_id,
            bank=BankOut(**group.bank.__dict__) if group.bank else None,
            total_paise=group.total_paise,
            next_due_by=group.next_due_by,
            earnings=[
                DueEarningOut(
                    id=item.earning.id,
                    booking_id=item.booking.id,
                    booking_starts_at=item.booking.starts_at,
                    kind=item.earning.kind.value,
                    amount_paise=item.earning.amount_paise,
                    minutes=item.earning.minutes,
                    due_by=item.earning.due_by,
                )
                for item in group.earnings
            ],
        )
        for group in found
    ]


class PayoutsSummaryOut(BaseModel):
    due: int
    overdue: int


@router.get("/payouts/summary")
def payouts_summary(admin: Admin, db: DbSession) -> PayoutsSummaryOut:
    """Counts only, for the banner on the admin home page: no details shown, nothing logged."""
    found = payouts_service.summary(db, datetime.now(UTC))
    return PayoutsSummaryOut(due=found.due, overdue=found.overdue)


class MarkPaidIn(BaseModel):
    earning_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)  # the ones shown on the list
    transfer_reference: str = Field(max_length=40)


class PayoutOut(BaseModel):
    id: uuid.UUID
    amount_paise: int
    method: str
    transfer_reference: str
    paid_at: datetime


@router.post("/payouts/{sitter_id}/paid")
def mark_payout_paid(
    sitter_id: uuid.UUID, body: MarkPaidIn, admin: Admin, db: DbSession, mailer: Mailer, settings: AppSettings
) -> PayoutOut:
    """Everything shown as due to her, paid in one transfer: recorded with its reference; she's emailed."""
    payout = payouts_service.mark_paid(db, admin.id, sitter_id, body.earning_ids, body.transfer_reference)
    profile = db.get(Profile, sitter_id)
    if profile is not None:
        mailer.send(
            email_service.payout_paid(
                profile.email, profile.full_name, payout.amount_paise, payout.method.value, _web_url(settings)
            )
        )
    return PayoutOut(
        id=payout.id,
        amount_paise=payout.amount_paise,
        method=payout.method.value,
        transfer_reference=payout.transfer_reference,
        paid_at=payout.paid_at,
    )


# ---------- low ratings (CLAUDE.md 6.11; phase 9) ----------


class RatingFlagOut(BaseModel):
    id: uuid.UUID
    sitter_id: uuid.UUID
    sitter_name: str | None
    sitter_phone: str | None
    average: float  # of her last 10 reviews when flagged
    reviews_counted: int
    status: str  # open (not told yet), told, responded
    created_at: datetime
    reason: str | None  # what she was told
    told_at: datetime | None
    response: str | None  # hers
    responded_at: datetime | None
    respond_by: datetime | None  # her 12 hours to respond end (Reuben, 2026-11-22)
    can_close: bool  # not told yet, or she has responded or her 12 hours have passed


def _flag_out(db, flag) -> RatingFlagOut:
    profile = db.get(Profile, flag.sitter_id)
    return RatingFlagOut(
        id=flag.id,
        sitter_id=flag.sitter_id,
        sitter_name=profile.full_name if profile else None,
        sitter_phone=profile.phone if profile else None,
        average=float(flag.average),
        reviews_counted=flag.reviews_counted,
        status=flag.status.value,
        created_at=flag.created_at,
        reason=flag.reason,
        told_at=flag.told_at,
        response=flag.response,
        responded_at=flag.responded_at,
        respond_by=reviews_service.respond_by(flag),
        can_close=flag.told_at is None or reviews_service.can_decide(flag, datetime.now(UTC)),
    )


@router.get("/rating-flags")
def get_rating_flags(admin: Admin, db: DbSession) -> list[RatingFlagOut]:
    """Sitters whose last-10 average fell below 3.5, not yet closed, oldest first."""
    return [_flag_out(db, flag) for flag in reviews_service.open_flags(db)]


class TellIn(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


@router.post("/rating-flags/{flag_id}/tell")
def tell_rating_flag(
    flag_id: uuid.UUID, body: TellIn, admin: Admin, db: DbSession, mailer: Mailer, settings: AppSettings
) -> RatingFlagOut:
    """Tells her the reason; she can then respond in the app (6.11). She's emailed."""
    flag = reviews_service.tell(db, admin.id, flag_id, body.reason, datetime.now(UTC))
    sitter = db.get(Profile, flag.sitter_id)
    if sitter is not None:
        mailer.send(email_service.rating_flag_told(sitter.email, sitter.full_name, flag.reason, _web_url(settings)))
    return _flag_out(db, flag)


class CloseFlagIn(BaseModel):
    note: str = Field(min_length=1, max_length=1000)


@router.post("/rating-flags/{flag_id}/close")
def close_rating_flag(flag_id: uuid.UUID, body: CloseFlagIn, admin: Admin, db: DbSession) -> RatingFlagOut:
    """The admin's decision, as an internal note. Removing her account is a separate step (phase 10)."""
    return _flag_out(db, reviews_service.close(db, admin.id, flag_id, body.note, datetime.now(UTC)))


# ---------- the dashboard (phase 10) ----------


class DashboardOut(BaseModel):
    """What's waiting, as counts (and amounts) only: no names or bank details, so it can refresh on a timer."""

    incidents_open: int  # not yet acknowledged
    incidents_unresolved: int
    sitters_to_review: int
    families_to_review: int
    payments_to_check: int
    refunds_to_pay: int
    payouts_due: int
    payouts_due_paise: int
    payouts_overdue: int
    paid_today: int  # India time
    paid_today_paise: int
    reports_open: int
    overdue_checkouts: int
    complaints_open: int
    complaints_overdue: int
    low_ratings: int


@router.get("/dashboard")
def get_dashboard(admin: Admin, db: DbSession) -> DashboardOut:
    return DashboardOut(**vars(dashboard_service.counts(db, datetime.now(UTC))))


# ---------- user management (phase 10; Reuben, 2026-11-22) ----------

PEOPLE_LIMIT = 50


def _like(text: str) -> str:
    """A LIKE pattern matching `text` anywhere, with its wildcards taken literally."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class PersonRow(BaseModel):
    id: uuid.UUID
    role: str  # parent | sitter
    full_name: str | None
    email: str
    phone: str | None
    status: str  # pending | active | suspended | removed
    created_at: datetime


@router.get("/people")
def list_people(
    admin: Admin, db: DbSession, q: str | None = None, role: Role | None = None, status: ProfileStatus | None = None
) -> list[PersonRow]:
    """Parents and sitters, newest first, found by name, email or phone (at most 50)."""
    query = select(Profile).where(Profile.role.in_((Role.parent, Role.sitter)))
    if role is not None:
        query = query.where(Profile.role == role)
    if status is not None:
        query = query.where(Profile.status == status)
    text = (q or "").strip()[:100]
    if text:
        query = query.where(
            or_(
                Profile.full_name.ilike(_like(text), escape="\\"),
                Profile.email.ilike(_like(text), escape="\\"),
                func.replace(Profile.phone, " ", "").ilike(_like(text.replace(" ", "")), escape="\\"),
            )
        )
    found = db.scalars(query.order_by(Profile.created_at.desc(), Profile.id).limit(PEOPLE_LIMIT))
    return [
        PersonRow(
            id=person.id,
            role=person.role.value,
            full_name=person.full_name,
            email=person.email,
            phone=person.phone,
            status=person.status.value,
            created_at=person.created_at,
        )
        for person in found
    ]


class AccountActionOut(BaseModel):
    action: str  # suspended | removed | reinstated
    kind: str | None  # low_ratings | safety | strikes | other
    reason: str
    by: str | None  # the admin's name; None when the rules did it
    at: datetime


class AccountOut(BaseModel):
    id: uuid.UUID
    role: str
    status: str
    upcoming_bookings: int  # what a suspension or removal would cancel and refund
    under_way_bookings: int  # left for an admin to handle
    ratings_wait: str | None  # sitters: why a low-ratings decision must wait, if it must
    five_strikes: bool  # a sitter can't be reinstated while 5 strikes count
    history: list[AccountActionOut]


def _account_out(db: DbSession, profile_id: uuid.UUID) -> AccountOut:
    profile = db.get(Profile, profile_id)
    if profile is None or profile.role not in (Role.parent, Role.sitter):
        raise AppError(404, "not_found", "We couldn't find that person.")
    now = datetime.now(UTC)
    rows = account_service.history(db, profile.id)
    admin_ids = {row.admin_id for row in rows if row.admin_id is not None}
    names: dict[uuid.UUID, str | None] = {}
    if admin_ids:
        names = dict(db.execute(select(Profile.id, Profile.full_name).where(Profile.id.in_(admin_ids))).all())
    return AccountOut(
        id=profile.id,
        role=profile.role.value,
        status=profile.status.value,
        upcoming_bookings=account_service.upcoming_count(db, profile.id, now),
        under_way_bookings=account_service.under_way_count(db, profile.id, now),
        ratings_wait=account_service.ratings_wait(db, profile, now) if profile.role == Role.sitter else None,
        five_strikes=account_service.five_strikes(db, profile, now),
        history=[
            AccountActionOut(
                action=row.action.value,
                kind=row.kind.value if row.kind else None,
                reason=row.reason,
                by=(names.get(row.admin_id) or "An admin") if row.admin_id else None,
                at=row.created_at,
            )
            for row in rows
        ],
    )


@router.get("/accounts/{profile_id}")
def get_account(profile_id: uuid.UUID, admin: Admin, db: DbSession) -> AccountOut:
    return _account_out(db, profile_id)


class BlockIn(BaseModel):
    kind: AccountActionKind
    reason: str = Field(max_length=account_service.REASON_MAX)  # shown to the person


class ReinstateIn(BaseModel):
    reason: str = Field(max_length=account_service.REASON_MAX)  # shown to the person


def _tell_blocked(
    db: DbSession, mailer: Mailer, settings: Settings, changed: account_service.Changed, removed: bool
) -> None:
    profile = changed.profile
    build = email_service.account_removed if removed else email_service.account_suspended
    mailer.send(build(profile.email, profile.full_name, changed.row.reason))
    for booking in changed.cancelled:
        if profile.role == Role.sitter:
            parent = db.get(Profile, booking.parent_id)
            assert parent is not None
            sent = payments_service.latest_booking_payment(db, booking.id)
            refunded = sent is not None and sent.status != PaymentStatus.rejected
            mailer.send(
                email_service.booking_cancelled_by_pacifyco_for_parent(
                    parent.email, parent.full_name, profile.full_name, booking.starts_at, refunded, _web_url(settings)
                )
            )
        elif booking.request_visible_at is not None:  # a request she never saw needs no email
            sitter = db.get(Profile, booking.sitter_id)
            assert sitter is not None
            mailer.send(
                email_service.booking_cancelled_by_pacifyco_for_sitter(
                    sitter.email, sitter.full_name, booking.starts_at, _web_url(settings)
                )
            )
    if profile.role == Role.sitter and changed.cancelled:
        for to in settings.admin_alert_emails:
            mailer.send(email_service.sitter_bookings_cancelled_alert(to, len(changed.cancelled), _web_url(settings)))


@router.post("/accounts/{profile_id}/suspend")
def suspend_account(
    profile_id: uuid.UUID, body: BlockIn, admin: Admin, db: DbSession, mailer: Mailer, settings: AppSettings
) -> AccountOut:
    """Suspends a parent or sitter: their upcoming bookings are cancelled and refunded, and they're emailed
    the reason. A low-ratings suspension waits for her response or the end of her 12 hours (6.11)."""
    changed = account_service.suspend(db, admin.id, profile_id, body.kind, body.reason, datetime.now(UTC))
    _tell_blocked(db, mailer, settings, changed, removed=False)
    return _account_out(db, profile_id)


@router.post("/accounts/{profile_id}/remove")
def remove_account(
    profile_id: uuid.UUID, body: BlockIn, admin: Admin, db: DbSession, mailer: Mailer, settings: AppSettings
) -> AccountOut:
    """Removes a parent or sitter, as a suspension does, for good unless reinstated."""
    changed = account_service.remove(db, admin.id, profile_id, body.kind, body.reason, datetime.now(UTC))
    _tell_blocked(db, mailer, settings, changed, removed=True)
    return _account_out(db, profile_id)


@router.post("/accounts/{profile_id}/reinstate")
def reinstate_account(
    profile_id: uuid.UUID, body: ReinstateIn, admin: Admin, db: DbSession, mailer: Mailer, settings: AppSettings
) -> AccountOut:
    """Makes a suspended or removed account usable again (active, or pending if never verified)."""
    changed = account_service.reinstate(db, admin.id, profile_id, body.reason, datetime.now(UTC))
    profile = changed.profile
    area = f"{_web_url(settings).rstrip('/')}/{profile.role.value}"
    mailer.send(email_service.account_reinstated(profile.email, profile.full_name, changed.row.reason, area))
    return _account_out(db, profile_id)


# ---------- the bookings overview and manual adjustments (phase 10; Reuben, 2026-11-23) ----------


class AdminBookingRow(BaseModel):
    id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    status: str
    plan: str
    price_paise: int
    parent_name: str | None
    sitter_name: str | None


class AdminBookingList(BaseModel):
    bookings: list[AdminBookingRow]
    more: bool  # another page follows


@router.get("/bookings")
def list_bookings(
    admin: Admin,
    db: DbSession,
    group: str | None = None,  # upcoming | under_way | past | cancelled
    q: str | None = None,  # the parent's or sitter's name
    starts_from: date | None = None,  # India dates, inclusive
    starts_to: date | None = None,
    page: Annotated[int, Query(ge=0, le=1000)] = 0,
) -> AdminBookingList:
    if group is not None and group not in admin_bookings_service.GROUPS:
        raise AppError(422, "invalid_group", "Choose upcoming, under way, past or cancelled.")
    found, more = admin_bookings_service.overview(
        db, datetime.now(UTC), group=group, q=q, starts_from=starts_from, starts_to=starts_to, page=page
    )
    return AdminBookingList(
        bookings=[
            AdminBookingRow(
                id=item.booking.id,
                starts_at=item.booking.starts_at,
                ends_at=item.booking.ends_at,
                status=item.booking.status.value,
                plan=item.booking.plan.value,
                price_paise=item.booking.price_paise,
                parent_name=item.parent_name,
                sitter_name=item.sitter_name,
            )
            for item in found
        ],
        more=more,
    )


class BookingPerson(BaseModel):
    id: uuid.UUID
    full_name: str | None
    email: str
    phone: str | None


class BookingMoney(BaseModel):
    id: uuid.UUID
    kind: str  # booking | overtime | refund | cancellation_charge
    amount_paise: int  # + paid or owed by the parent, − refunded
    status: str  # pending | confirmed | rejected | waived
    upi_reference: str | None
    transfer_reference: str | None
    rejection_reason: str | None
    waive_reason: str | None
    created_at: datetime
    decided_at: datetime | None
    can_waive: bool  # an unpaid charge with no payment waiting to be checked


class BookingEarning(BaseModel):
    id: uuid.UUID
    kind: str  # booking | overtime | show_up_fee | adjustment
    amount_paise: int
    minutes: int | None
    note: str | None
    status: str  # held | released | paid
    due_by: datetime | None


class BookingEvent(BaseModel):
    action: str
    by: str | None  # the person's name; None when the rules did it
    at: datetime
    after: dict | None


class AdminBookingDetail(BaseModel):
    id: uuid.UUID
    status: str
    plan: str
    units: int
    children: list[str]
    starts_at: datetime
    ends_at: datetime
    price_paise: int
    created_at: datetime
    parent: BookingPerson
    sitter: BookingPerson
    checked_in_at: datetime | None
    checked_out_at: datetime | None
    codes_locked: bool
    close_reason: str | None
    payments: list[BookingMoney]
    earnings: list[BookingEarning]
    refundable_paise: int
    can_cancel: bool
    can_add_pay: bool
    history: list[BookingEvent]


def _person(profile: Profile) -> BookingPerson:
    return BookingPerson(id=profile.id, full_name=profile.full_name, email=profile.email, phone=profile.phone)


def _admin_booking(db: DbSession, booking_id: uuid.UUID) -> AdminBookingDetail:
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise AppError(404, "not_found", "We couldn't find that booking.")
    db.refresh(booking)
    parent, sitter = _people(db, booking)
    assert sitter is not None
    now = datetime.now(UTC)
    money = db.scalars(select(Payment).where(Payment.booking_id == booking.id).order_by(Payment.created_at)).all()
    earned = db.scalars(
        select(SitterEarning).where(SitterEarning.booking_id == booking.id).order_by(SitterEarning.created_at)
    ).all()
    children = db.scalars(
        select(Child.name)
        .join(BookingChild, BookingChild.child_id == Child.id)
        .where(BookingChild.booking_id == booking.id)
        .order_by(Child.name)
    ).all()
    about = [str(booking.id), *(str(item.id) for item in money), *(str(item.id) for item in earned)]
    events = db.execute(
        select(AuditLog, Profile.full_name)
        .outerjoin(Profile, Profile.id == AuditLog.actor_id)
        .where(AuditLog.entity_id.in_(about))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(200)
    ).all()
    return AdminBookingDetail(
        id=booking.id,
        status=booking.status.value,
        plan=booking.plan.value,
        units=booking.units,
        children=list(children),
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
        price_paise=booking.price_paise,
        created_at=booking.created_at,
        parent=_person(parent),
        sitter=_person(sitter),
        checked_in_at=booking.checked_in_at,
        checked_out_at=booking.checked_out_at,
        codes_locked=booking.codes_locked,
        close_reason=booking.close_reason,
        payments=[
            BookingMoney(
                id=item.id,
                kind=item.kind.value,
                amount_paise=item.amount_paise,
                status=item.status.value,
                upi_reference=item.upi_reference,
                transfer_reference=item.transfer_reference,
                rejection_reason=item.rejection_reason,
                waive_reason=item.waive_reason,
                created_at=item.created_at,
                decided_at=item.confirmed_at,
                can_waive=item.kind in admin_bookings_service.CHARGE_KINDS
                and item.status == PaymentStatus.pending
                and item.upi_reference is None,
            )
            for item in money
        ],
        earnings=[
            BookingEarning(
                id=item.id,
                kind=item.kind.value,
                amount_paise=item.amount_paise,
                minutes=item.minutes,
                note=item.note,
                status=item.status.value,
                due_by=item.due_by,
            )
            for item in earned
        ],
        refundable_paise=admin_bookings_service.refundable_paise(db, booking.id),
        can_cancel=booking.status in admin_bookings_service.UPCOMING and booking.starts_at > now,
        can_add_pay=booking.status not in (*admin_bookings_service.UPCOMING, BookingStatus.in_progress),
        history=[
            BookingEvent(
                action=event.action,
                by=(name or "Someone") if event.actor_id else None,
                at=event.created_at,
                after=event.after,
            )
            for event, name in events
        ],
    )


@router.get("/bookings/{booking_id}")
def get_admin_booking(booking_id: uuid.UUID, admin: Admin, db: DbSession) -> AdminBookingDetail:
    return _admin_booking(db, booking_id)


class AdjustReasonIn(BaseModel):
    reason: str = Field(max_length=admin_bookings_service.REASON_MAX)


class AdjustAmountIn(BaseModel):
    amount_paise: int = Field(gt=0, le=10_000_000)
    reason: str = Field(max_length=admin_bookings_service.REASON_MAX)


@router.post("/bookings/{booking_id}/cancel")
def cancel_booking(
    booking_id: uuid.UUID, body: AdjustReasonIn, admin: Admin, db: DbSession, mailer: Mailer, settings: AppSettings
) -> AdminBookingDetail:
    """Cancels a booking that hasn't started: refunded in full, no strike, both told with the reason."""
    done = admin_bookings_service.cancel(db, admin.id, booking_id, body.reason, datetime.now(UTC))
    booking = done.booking
    parent, sitter = _people(db, booking)
    assert sitter is not None
    sent = payments_service.latest_booking_payment(db, booking.id)
    refunded = sent is not None and sent.status != PaymentStatus.rejected
    mailer.send(
        email_service.booking_cancelled_by_admin_for_parent(
            parent.email,
            parent.full_name,
            sitter.full_name,
            booking.starts_at,
            refunded,
            done.reason,
            _web_url(settings),
        )
    )
    if done.was_accepted:
        mailer.send(
            email_service.booking_cancelled_by_admin_for_sitter(
                sitter.email, sitter.full_name, booking.starts_at, done.reason, _web_url(settings)
            )
        )
    return _admin_booking(db, booking_id)


@router.post("/bookings/{booking_id}/refund")
def refund_part(
    booking_id: uuid.UUID, body: AdjustAmountIn, admin: Admin, db: DbSession, mailer: Mailer, settings: AppSettings
) -> AdminBookingDetail:
    """A refund of part of what was paid, owed to the parent until an admin pays it back and marks it paid."""
    booking, row = admin_bookings_service.refund(db, admin.id, booking_id, body.amount_paise, body.reason)
    parent, _ = _people(db, booking)
    mailer.send(
        email_service.partial_refund(
            parent.email, parent.full_name, -row.amount_paise, body.reason.strip(), _web_url(settings)
        )
    )
    return _admin_booking(db, booking_id)


@router.post("/bookings/{booking_id}/sitter-pay")
def add_sitter_pay(
    booking_id: uuid.UUID, body: AdjustAmountIn, admin: Admin, db: DbSession, mailer: Mailer, settings: AppSettings
) -> AdminBookingDetail:
    """Extra pay for the sitter, with a note she sees: paid within 12 hours like her other earnings."""
    earning = admin_bookings_service.add_pay(
        db, admin.id, booking_id, body.amount_paise, body.reason, datetime.now(UTC)
    )
    sitter = db.get(Profile, earning.sitter_id)
    assert sitter is not None
    mailer.send(
        email_service.extra_pay(
            sitter.email, sitter.full_name, earning.amount_paise, earning.note or "", _web_url(settings)
        )
    )
    return _admin_booking(db, booking_id)


@router.post("/charges/{payment_id}/waive")
def waive_charge(
    payment_id: uuid.UUID, body: AdjustReasonIn, admin: Admin, db: DbSession, mailer: Mailer, settings: AppSettings
) -> AdminBookingDetail:
    """Lets an unpaid overtime or cancellation charge go: no longer owed, so it stops blocking bookings."""
    charge = admin_bookings_service.waive(db, admin.id, payment_id, body.reason, datetime.now(UTC))
    parent = db.get(Profile, charge.parent_id)
    assert parent is not None
    mailer.send(
        email_service.charge_waived(
            parent.email, parent.full_name, charge.amount_paise, charge.waive_reason or "", _web_url(settings)
        )
    )
    return _admin_booking(db, charge.booking_id)


# ---------- the audit log and the document access log (phase 10) ----------


class AdminOption(BaseModel):
    id: uuid.UUID
    full_name: str | None


@router.get("/admins")
def list_admins(admin: Admin, db: DbSession) -> list[AdminOption]:
    """Every admin, for the logs' "who did it" filters."""
    found = admin_logs_service.admins(db)
    return [AdminOption(id=id, full_name=name) for id, name in sorted(found, key=lambda item: item[1] or "")]


class LogPerson(BaseModel):
    id: uuid.UUID
    full_name: str | None
    role: str


class AuditEntryOut(BaseModel):
    id: int
    at: datetime
    by: str | None  # the admin's or person's name; None when the rules did it
    by_id: uuid.UUID | None
    action: str
    entity: str
    entity_id: str
    person: LogPerson | None  # who the row is about, when it's about a person
    before: dict | None
    after: dict | None


class AuditLogPage(BaseModel):
    entries: list[AuditEntryOut]
    more: bool


@router.get("/audit-log")
def get_audit_log(
    admin: Admin,
    db: DbSession,
    by: str | None = None,  # an admin's id, or "rules" for what the rules did
    entity: Annotated[str | None, Query(max_length=40)] = None,
    entity_id: Annotated[str | None, Query(max_length=100)] = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
    on_from: date | None = None,  # India dates, inclusive
    on_to: date | None = None,
    page: Annotated[int, Query(ge=0, le=1000)] = 0,
) -> AuditLogPage:
    actor_id = None
    if by and by != "rules":
        try:
            actor_id = uuid.UUID(by)
        except ValueError:
            raise AppError(422, "invalid_actor", "Choose an admin from the list.") from None
    found, more = admin_logs_service.audit_entries(
        db,
        actor_id=actor_id,
        by_rules=by == "rules",
        entity=entity,
        entity_id=entity_id,
        action=action,
        on_from=on_from,
        on_to=on_to,
        page=page,
    )
    return AuditLogPage(
        entries=[
            AuditEntryOut(
                id=item.row.id,
                at=item.row.created_at,
                by=(item.actor_name or "Someone") if item.row.actor_id else None,
                by_id=item.row.actor_id,
                action=item.row.action,
                entity=item.row.entity,
                entity_id=item.row.entity_id,
                person=LogPerson(id=item.person.id, full_name=item.person.name, role=item.person.role.value)
                if item.person
                else None,
                before=item.row.before,
                after=item.row.after,
            )
            for item in found
        ],
        more=more,
    )


class DocumentViewOut(BaseModel):
    id: int
    at: datetime
    admin_name: str | None
    admin_id: uuid.UUID
    document_id: uuid.UUID
    document_type: str
    deleted: bool  # the file has since been deleted (birth certificates, once the child is verified)
    owner: LogPerson
    child_name: str | None


class DocumentViewsPage(BaseModel):
    views: list[DocumentViewOut]
    more: bool


@router.get("/document-access-log")
def get_document_access_log(
    admin: Admin,
    db: DbSession,
    admin_id: uuid.UUID | None = None,
    document_type: DocumentType | None = None,
    owner: Annotated[str | None, Query(max_length=100)] = None,  # the owner's name
    owner_id: uuid.UUID | None = None,
    on_from: date | None = None,  # India dates, inclusive
    on_to: date | None = None,
    page: Annotated[int, Query(ge=0, le=1000)] = 0,
) -> DocumentViewsPage:
    found, more = admin_logs_service.document_views(
        db,
        admin_id=admin_id,
        document_type=document_type,
        owner=owner,
        owner_id=owner_id,
        on_from=on_from,
        on_to=on_to,
        page=page,
    )
    return DocumentViewsPage(
        views=[
            DocumentViewOut(
                id=item.row.id,
                at=item.row.accessed_at,
                admin_name=item.admin_name,
                admin_id=item.row.admin_id,
                document_id=item.document.id,
                document_type=item.document.type.value,
                deleted=item.document.deleted_at is not None,
                owner=LogPerson(id=item.owner.id, full_name=item.owner.name, role=item.owner.role.value),
                child_name=item.child_name,
            )
            for item in found
        ],
        more=more,
    )


# ---------- complaints, appeals and the Grievance Officer (CLAUDE.md 6.12; phase 10) ----------


class ComplaintPerson(BaseModel):
    id: uuid.UUID
    full_name: str | None
    role: str
    email: str
    phone: str | None
    status: str


class AdminComplaintRow(BaseModel):
    id: uuid.UUID
    type: str
    topic: str | None
    request_kind: str | None  # a data request: access, correction or deletion
    status: str
    person_name: str | None
    person_role: str
    created_at: datetime
    reply_by: datetime
    resolve_by: datetime
    first_reply_at: datetime | None
    escalated_at: datetime | None
    officer_acknowledged_at: datetime | None
    late: bool
    serious: bool
    overdue: bool


class AdminComplaintMessage(BaseModel):
    id: uuid.UUID
    from_pacifyco: bool
    by: str | None
    body: str
    at: datetime


class AppealDecision(BaseModel):
    action: str  # suspended | removed
    kind: str | None
    reason: str
    at: datetime
    by: str | None  # the admin's name; None when the rules did it
    by_id: uuid.UUID | None


class AdminComplaint(AdminComplaintRow):
    description: str
    happened_on: date | None
    person: ComplaintPerson
    booking_id: uuid.UUID | None
    booking_starts_at: datetime | None
    resolution: str | None
    resolved_at: datetime | None
    appeal_outcome: str | None
    decision: AppealDecision | None  # an appeal: what it's against
    escalation_note: str | None
    escalated_by_person: bool
    acknowledge_by: datetime | None
    decide_by: datetime | None
    officer_decision: str | None
    officer_decided_at: datetime | None
    messages: list[AdminComplaintMessage]
    attachments: list[DocumentSummary]
    cannot_handle: str | None  # why this admin may not act on it
    is_officer: bool


def _complaint_row(db: DbSession, complaint: Complaint, now: datetime) -> AdminComplaintRow:
    person = db.get(Profile, complaint.raised_by)
    return AdminComplaintRow(
        id=complaint.id,
        type=complaint.type.value,
        topic=complaint.topic.value if complaint.topic else None,
        request_kind=complaint.request_kind.value if complaint.request_kind else None,
        status=complaint.status.value,
        person_name=person.full_name,
        person_role=person.role.value,
        created_at=complaint.created_at,
        reply_by=complaint.reply_by,
        resolve_by=complaint.resolve_by,
        first_reply_at=complaint.first_reply_at,
        escalated_at=complaint.escalated_at,
        officer_acknowledged_at=complaint.officer_acknowledged_at,
        late=complaint.late,
        serious=complaint.serious,
        overdue=complaints_service.overdue(complaint, now),
    )


def _admin_complaint(db: DbSession, settings: Settings, admin: Profile, complaint_id: uuid.UUID) -> AdminComplaint:
    complaint = db.get(Complaint, complaint_id)
    if complaint is None:
        raise AppError(404, "not_found", "We couldn't find that complaint.")
    db.refresh(complaint)
    now = datetime.now(UTC)
    person = db.get(Profile, complaint.raised_by)
    booking = db.get(Booking, complaint.booking_id) if complaint.booking_id else None
    decision = complaints_service.decision_of(db, complaint)
    decider = db.get(Profile, decision.admin_id) if decision and decision.admin_id else None
    thread = complaints_service.messages(db, complaint.id)
    authors = {item.author_id for item in thread}
    names = {row.id: row.full_name for row in db.scalars(select(Profile).where(Profile.id.in_(authors)))}
    escalated = complaint.escalated_at
    return AdminComplaint(
        **_complaint_row(db, complaint, now).model_dump(),
        description=complaint.description,
        happened_on=complaint.happened_on,
        person=ComplaintPerson(
            id=person.id,
            full_name=person.full_name,
            role=person.role.value,
            email=person.email,
            phone=person.phone,
            status=person.status.value,
        ),
        booking_id=booking.id if booking else None,
        booking_starts_at=booking.starts_at if booking else None,
        resolution=complaint.resolution,
        resolved_at=complaint.resolved_at,
        appeal_outcome=complaint.appeal_outcome.value if complaint.appeal_outcome else None,
        decision=AppealDecision(
            action=decision.action.value,
            kind=decision.kind.value if decision.kind else None,
            reason=decision.reason,
            at=decision.created_at,
            by=decider.full_name if decider else None,
            by_id=decision.admin_id,
        )
        if decision
        else None,
        escalation_note=complaint.escalation_note,
        escalated_by_person=complaint.escalated_by is not None,
        acknowledge_by=escalated + complaints_service.OFFICER_ACKNOWLEDGE_WITHIN if escalated else None,
        decide_by=escalated + complaints_service.OFFICER_DECIDE_WITHIN if escalated else None,
        officer_decision=complaint.officer_decision,
        officer_decided_at=complaint.officer_decided_at,
        messages=[
            AdminComplaintMessage(
                id=item.id,
                from_pacifyco=item.author_id != complaint.raised_by,
                by=names.get(item.author_id),
                body=item.body,
                at=item.created_at,
            )
            for item in thread
        ],
        attachments=[
            DocumentSummary(id=item.id, type=item.type.value, uploaded_at=item.created_at)
            for item in complaints_service.attachments(db, complaint.id)
        ],
        cannot_handle=complaints_service.can_handle(db, settings, admin, complaint),
        is_officer=complaints_service.is_officer(settings, admin),
    )


@router.get("/complaints")
def list_complaints(admin: Admin, db: DbSession, view: str = "open") -> list[AdminComplaintRow]:
    """open (soonest target first) | appeals | escalated | done (the latest 100)."""
    if view not in complaints_service.VIEWS:
        raise AppError(422, "invalid_view", "Choose open, appeals, escalated or done.")
    now = datetime.now(UTC)
    return [_complaint_row(db, item, now) for item in complaints_service.queue(db, view)]


@router.get("/complaints/{complaint_id}")
def get_complaint(complaint_id: uuid.UUID, admin: Admin, db: DbSession, settings: AppSettings) -> AdminComplaint:
    return _admin_complaint(db, settings, admin, complaint_id)


class ComplaintTextIn(BaseModel):
    body: str = Field(max_length=complaints_service.TEXT_MAX)


@router.post("/complaints/{complaint_id}/messages")
def reply_to_complaint(
    complaint_id: uuid.UUID, body: ComplaintTextIn, admin: Admin, db: DbSession, settings: AppSettings, mailer: Mailer
) -> AdminComplaint:
    complaint = complaints_service.admin_writes(db, settings, admin, complaint_id, body.body, datetime.now(UTC))
    complaint_mail.tell_admin_wrote(db, mailer, settings, complaint, body.body.strip())
    return _admin_complaint(db, settings, admin, complaint_id)


class SeriousIn(BaseModel):
    serious: bool


@router.post("/complaints/{complaint_id}/serious")
def mark_complaint_serious(
    complaint_id: uuid.UUID, body: SeriousIn, admin: Admin, db: DbSession, settings: AppSettings
) -> AdminComplaint:
    complaints_service.mark_serious(db, settings, admin, complaint_id, body.serious, datetime.now(UTC))
    return _admin_complaint(db, settings, admin, complaint_id)


@router.post("/complaints/{complaint_id}/resolve")
def resolve_complaint(
    complaint_id: uuid.UUID, body: ComplaintTextIn, admin: Admin, db: DbSession, settings: AppSettings, mailer: Mailer
) -> AdminComplaint:
    complaint = complaints_service.resolve(db, settings, admin, complaint_id, body.body, datetime.now(UTC))
    complaint_mail.tell_resolved(db, mailer, settings, complaint)
    return _admin_complaint(db, settings, admin, complaint_id)


class AppealIn(BaseModel):
    outcome: AppealOutcome
    note: str = Field(max_length=complaints_service.TEXT_MAX)
    reinstate: bool = False  # upheld only: reinstate the account now (otherwise by hand, later)


@router.post("/complaints/{complaint_id}/appeal")
def decide_appeal(
    complaint_id: uuid.UUID, body: AppealIn, admin: Admin, db: DbSession, settings: AppSettings, mailer: Mailer
) -> AdminComplaint:
    complaint = complaints_service.decide_appeal(
        db, settings, admin, complaint_id, body.outcome, body.note, body.reinstate, datetime.now(UTC)
    )
    complaint_mail.tell_appeal_decided(db, mailer, settings, complaint, body.reinstate)
    return _admin_complaint(db, settings, admin, complaint_id)


@router.post("/complaints/{complaint_id}/acknowledge")
def officer_acknowledge(complaint_id: uuid.UUID, admin: Admin, db: DbSession, settings: AppSettings) -> AdminComplaint:
    complaints_service.officer_acknowledges(db, settings, admin, complaint_id, datetime.now(UTC))
    return _admin_complaint(db, settings, admin, complaint_id)


@router.post("/complaints/{complaint_id}/officer-decision")
def officer_decide(
    complaint_id: uuid.UUID, body: ComplaintTextIn, admin: Admin, db: DbSession, settings: AppSettings, mailer: Mailer
) -> AdminComplaint:
    complaint = complaints_service.officer_decides(db, settings, admin, complaint_id, body.body, datetime.now(UTC))
    complaint_mail.tell_officer_decided(db, mailer, settings, complaint)
    return _admin_complaint(db, settings, admin, complaint_id)


class HolidayIn(BaseModel):
    day: date
    name: str = Field(max_length=100)


class HolidayOut(BaseModel):
    day: date
    name: str


@router.get("/holidays")
def list_holidays(admin: Admin, db: DbSession) -> list[HolidayOut]:
    """From the start of last year on: not working days for appeals (6.12)."""
    since = date(today_in_india(datetime.now(UTC)).year - 1, 1, 1)
    return [HolidayOut(day=item.day, name=item.name) for item in complaints_service.holidays(db, since)]


@router.post("/holidays", status_code=201)
def add_holiday(body: HolidayIn, admin: Admin, db: DbSession) -> list[HolidayOut]:
    complaints_service.add_holiday(db, admin.id, body.day, body.name)
    return list_holidays(admin, db)


@router.delete("/holidays/{day}")
def remove_holiday(day: date, admin: Admin, db: DbSession) -> list[HolidayOut]:
    complaints_service.remove_holiday(db, admin.id, day)
    return list_holidays(admin, db)
