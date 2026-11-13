"""The admin verification queue (CLAUDE.md 7, phase 3).

Sitters: an admin reviews the profile, ID documents and police certificate (`onboarding_steps`), each
reference (`references.outcome`) and the psychology test (`psych_attempts`, reviewed in
`app.services.psych_tests`), sets her level (6.2), then approves her. She is live -- shown to parents
and bookable -- only once approved with a level and an active account (`is_live`).

Families: an admin views each child's birth certificate (logged, `app.services.documents`) and
approves or rejects the child. On approval the birth certificate is deleted at once, keeping only the
status, verifier and date (CLAUDE.md 7).

Every decision writes to `audit_log` (CLAUDE.md 5).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import (
    Child,
    Document,
    DocumentStatus,
    DocumentType,
    OnboardingStatus,
    OnboardingStep,
    OnboardingStepName,
    Parent,
    Profile,
    ProfileStatus,
    PsychAttemptStatus,
    Reference,
    Sitter,
    SitterLevel,
    VerificationStatus,
)
from app.services import accounts, audit, encryption, legal, psych_tests
from app.services.storage import StorageClient

# Every step that must be approved before a sitter can be approved, in CLAUDE.md 7 order.
REVIEWED_STEPS = ("profile", "identity_documents", "police_certificate", "references", "psych_test")
# Optional since 2026-11-13 (Reuben): a sitter may give one reference, or none.
REQUIRED_REFERENCES = 0

_PSYCH_TO_STEP = {
    PsychAttemptStatus.passed: VerificationStatus.approved,
    PsychAttemptStatus.failed: VerificationStatus.rejected,
}


def _now() -> datetime:
    return datetime.now(UTC)


def _decision(approved: bool) -> VerificationStatus:
    return VerificationStatus.approved if approved else VerificationStatus.rejected


# ---------- sitters ----------


def get_sitter(db: Session, sitter_id: uuid.UUID) -> tuple[Profile, Sitter]:
    sitter = db.get(Sitter, sitter_id)
    profile = db.get(Profile, sitter_id)
    if sitter is None or profile is None:
        raise AppError(404, "not_found", "That sitter doesn't exist")
    return profile, sitter


def step_statuses(db: Session, sitter_id: uuid.UUID) -> dict[str, VerificationStatus]:
    """Where each onboarding step stands. Anything not yet approved or rejected is `pending`."""
    statuses = {name: VerificationStatus.pending for name in REVIEWED_STEPS}
    for row in db.scalars(select(OnboardingStep).where(OnboardingStep.sitter_id == sitter_id)):
        statuses[row.step.value] = row.status

    # References are optional: none passes; one she gives must be approved (a rejected one must go).
    outcomes = [reference.outcome for reference in sitter_references(db, sitter_id)]
    if VerificationStatus.rejected in outcomes:
        statuses["references"] = VerificationStatus.rejected
    elif all(o == VerificationStatus.approved for o in outcomes):
        statuses["references"] = VerificationStatus.approved

    attempt = psych_tests.latest_attempt(db, sitter_id)
    if attempt is not None:
        statuses["psych_test"] = _PSYCH_TO_STEP.get(attempt.status, VerificationStatus.pending)
    return statuses


def sitter_references(db: Session, sitter_id: uuid.UUID) -> list[Reference]:
    return list(
        db.scalars(
            select(Reference)
            .where(Reference.sitter_id == sitter_id, Reference.removed_at.is_(None))
            .order_by(Reference.id)
        )
    )


def sitter_documents(db: Session, sitter_id: uuid.UUID) -> list[Document]:
    """Her uploaded files, newest first. Failed or unfinished uploads aren't worth an admin's time."""
    return list(
        db.scalars(
            select(Document)
            .where(
                Document.owner_profile_id == sitter_id,
                Document.status == DocumentStatus.uploaded,
                Document.deleted_at.is_(None),
            )
            .order_by(Document.created_at.desc())
        )
    )


def record_step(
    db: Session,
    admin_id: uuid.UUID,
    sitter_id: uuid.UUID,
    step: OnboardingStepName,
    approved: bool,
    notes: str | None,
    rejection_reason: str | None = None,
) -> OnboardingStep:
    get_sitter(db, sitter_id)
    row = db.get(OnboardingStep, (sitter_id, step))
    before = {"status": row.status.value} if row is not None else None
    if row is None:
        row = OnboardingStep(sitter_id=sitter_id, step=step)
        db.add(row)
    row.status = _decision(approved)
    row.notes = notes
    row.rejection_reason = None if approved else rejection_reason
    row.reviewed_by = admin_id
    row.reviewed_at = _now()
    audit.record(
        db,
        admin_id,
        "onboarding_step_reviewed",
        "onboarding_steps",
        f"{sitter_id}:{step.value}",
        before=before,
        after={"status": row.status.value},
    )
    db.commit()
    return row


# Which onboarding step each sitter document belongs to (CLAUDE.md 7 steps 1-3).
DOCUMENT_STEPS = {
    DocumentType.photo: OnboardingStepName.profile,
    DocumentType.first_aid_certificate: OnboardingStepName.profile,
    DocumentType.government_id: OnboardingStepName.identity_documents,
    DocumentType.college_or_work_id: OnboardingStepName.identity_documents,
    DocumentType.police_certificate: OnboardingStepName.police_certificate,
}


def resubmitted(db: Session, sitter_id: uuid.UUID, step: OnboardingStepName) -> None:
    """She changed something in a rejected step: it goes back to waiting for review (decided
    2026-11-09). The caller commits. The psychology test is different: an admin allows a retake."""
    row = db.get(OnboardingStep, (sitter_id, step))
    if row is not None and row.status == VerificationStatus.rejected:
        row.status = VerificationStatus.pending
        row.rejection_reason = None


def record_reference_outcome(
    db: Session,
    admin_id: uuid.UUID,
    reference_id: uuid.UUID,
    approved: bool,
    notes: str | None,
    rejection_reason: str | None = None,
) -> Reference:
    reference = db.get(Reference, reference_id)
    if reference is None:
        raise AppError(404, "not_found", "That reference doesn't exist")
    before = {"outcome": reference.outcome.value}
    reference.outcome = _decision(approved)
    reference.notes = notes
    reference.rejection_reason = None if approved else rejection_reason
    audit.record(
        db,
        admin_id,
        "reference_reviewed",
        "references",
        str(reference.id),
        before=before,
        after={"outcome": reference.outcome.value},
    )
    db.commit()
    return reference


def set_level(db: Session, admin_id: uuid.UUID, sitter_id: uuid.UUID, level: SitterLevel) -> Sitter:
    """Admins set every sitter's level, new ones too, and move her up later (CLAUDE.md 6.2)."""
    _, sitter = get_sitter(db, sitter_id)
    before = {"level": sitter.level.value if sitter.level else None}
    sitter.level = level
    audit.record(
        db, admin_id, "sitter_level_set", "sitters", str(sitter_id), before=before, after={"level": level.value}
    )
    db.commit()
    return sitter


def decide_sitter(
    db: Session,
    admin_id: uuid.UUID,
    sitter_id: uuid.UUID,
    approved: bool,
    notes: str | None,
    rejection_reason: str | None = None,
) -> Sitter:
    """The last onboarding step (CLAUDE.md 7 step 6). Approving needs every step approved and a level."""
    profile, sitter = get_sitter(db, sitter_id)
    if approved:
        unfinished = [
            name for name, status in step_statuses(db, sitter_id).items() if status != VerificationStatus.approved
        ]
        if unfinished:
            raise AppError(
                409, "steps_not_approved", "Every onboarding step must be approved first", {"steps": unfinished}
            )
        if sitter.level is None:
            raise AppError(409, "level_not_set", "Set her level before approving her")
        if not accounts.details_complete(profile):
            raise AppError(409, "details_missing", "She hasn't filled in her name, mobile, pin code and address yet")
        if legal.outstanding(db, profile.id, profile.role):
            raise AppError(409, "consent_missing", "She hasn't accepted the sitter consent and terms yet")
        if sitter.payout_method is None:  # its own step since 2026-11-13, so check it here
            raise AppError(409, "payout_missing", "She hasn't added how she'd like to be paid yet")

    before = {"onboarding_status": sitter.onboarding_status.value, "profile_status": profile.status.value}
    sitter.onboarding_status = OnboardingStatus.approved if approved else OnboardingStatus.rejected
    sitter.rejection_reason = None if approved else rejection_reason
    if approved and profile.status == ProfileStatus.pending:  # never reinstates a suspended or removed account
        profile.status = ProfileStatus.active
    audit.record(
        db,
        admin_id,
        "sitter_approved" if approved else "sitter_rejected",
        "sitters",
        str(sitter_id),
        before=before,
        after={
            "onboarding_status": sitter.onboarding_status.value,
            "profile_status": profile.status.value,
            "notes": notes,
        },
    )
    db.commit()
    return sitter


def is_live(profile: Profile, sitter: Sitter) -> bool:
    """Shown to parents and bookable (CLAUDE.md 7, 9 "Sitter onboarding"). Search (phase 5) uses this."""
    return (
        profile.status == ProfileStatus.active
        and sitter.onboarding_status == OnboardingStatus.approved
        and sitter.level is not None
    )


def view_health_disclosure(db: Session, admin_id: uuid.UUID, sitter_id: uuid.UUID, encryption_key: str) -> str | None:
    """Health data: admin-only, and every view is logged (CLAUDE.md 7 step 1)."""
    _, sitter = get_sitter(db, sitter_id)
    audit.record(db, admin_id, "health_disclosure_viewed", "sitters", str(sitter_id))
    db.commit()
    if sitter.health_disclosure_encrypted is None:
        return None
    return encryption.decrypt(encryption_key, sitter.health_disclosure_encrypted)


@dataclass(frozen=True)
class SitterInQueue:
    profile: Profile
    sitter: Sitter
    steps_approved: int


def sitters_to_review(db: Session) -> list[SitterInQueue]:
    """Sitters still in onboarding, oldest sign-up first."""
    rows = db.execute(
        select(Profile, Sitter)
        .join(Sitter, Sitter.profile_id == Profile.id)
        .where(Sitter.onboarding_status == OnboardingStatus.in_progress)
        .order_by(Profile.created_at)
    ).all()
    queue = []
    for profile, sitter in rows:
        statuses = step_statuses(db, sitter.profile_id)
        approved = sum(1 for status in statuses.values() if status == VerificationStatus.approved)
        queue.append(SitterInQueue(profile=profile, sitter=sitter, steps_approved=approved))
    return queue


# ---------- families ----------


def _has_birth_certificate():
    return exists().where(
        Document.child_id == Child.id,
        Document.type == DocumentType.birth_certificate,
        Document.status == DocumentStatus.uploaded,
        Document.deleted_at.is_(None),
    )


@dataclass(frozen=True)
class FamilyInQueue:
    profile: Profile
    children_to_review: int


def families_to_review(db: Session) -> list[FamilyInQueue]:
    """Parents with a child waiting for review whose birth certificate is uploaded."""
    rows = db.execute(
        select(Profile, func.count(Child.id))
        .join(Child, Child.parent_id == Profile.id)
        .where(Child.verification_status == VerificationStatus.pending, _has_birth_certificate())
        .group_by(Profile.id)
        .order_by(Profile.created_at)
    ).all()
    return [FamilyInQueue(profile=profile, children_to_review=count) for profile, count in rows]


def get_parent(db: Session, parent_id: uuid.UUID) -> tuple[Profile, Parent]:
    parent = db.get(Parent, parent_id)
    profile = db.get(Profile, parent_id)
    if parent is None or profile is None:
        raise AppError(404, "not_found", "That parent doesn't exist")
    return profile, parent


def birth_certificates(db: Session, child_id: uuid.UUID) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(
                Document.child_id == child_id,
                Document.type == DocumentType.birth_certificate,
                Document.status == DocumentStatus.uploaded,
                Document.deleted_at.is_(None),
            )
            .order_by(Document.created_at.desc())
        )
    )


def decide_child(
    db: Session,
    storage: StorageClient,
    admin_id: uuid.UUID,
    child_id: uuid.UUID,
    approved: bool,
    notes: str | None,
    rejection_reason: str | None = None,
) -> Child:
    child = db.get(Child, child_id)
    if child is None:
        raise AppError(404, "not_found", "That child doesn't exist")
    certificates = birth_certificates(db, child_id)
    if approved and not certificates:
        raise AppError(409, "no_birth_certificate", "There's no birth certificate to check for this child")

    before = {"verification_status": child.verification_status.value}
    child.verification_status = _decision(approved)
    child.verified_by = admin_id
    child.verified_at = _now()
    child.verification_notes = notes
    child.rejection_reason = None if approved else rejection_reason
    audit.record(
        db,
        admin_id,
        "child_verified" if approved else "child_rejected",
        "children",
        str(child.id),
        before=before,
        after={"verification_status": child.verification_status.value},
    )

    if approved:
        # Deleted at once, keeping status, verifier and date (CLAUDE.md 7). If Storage fails, nothing is
        # committed and the admin can simply try again.
        for document in certificates:
            storage.delete(document.storage_path)
            document.deleted_at = _now()
        _approve_parent(db, admin_id, child.parent_id)
    db.commit()
    return child


def _approve_parent(db: Session, admin_id: uuid.UUID, parent_id: uuid.UUID) -> None:
    """A family is verified once an admin has approved every child's birth certificate (CLAUDE.md 7,
    decided 2026-11-08). Never reinstates a suspended or removed account."""
    profile, parent = get_parent(db, parent_id)
    if parent.verification_status == VerificationStatus.approved:
        return
    statuses = db.scalars(select(Child.verification_status).where(Child.parent_id == parent_id))
    if any(status != VerificationStatus.approved for status in statuses):
        return
    before = {"verification_status": parent.verification_status.value, "profile_status": profile.status.value}
    parent.verification_status = VerificationStatus.approved
    if profile.status == ProfileStatus.pending:
        profile.status = ProfileStatus.active
    audit.record(
        db,
        admin_id,
        "parent_verified",
        "parents",
        str(parent_id),
        before=before,
        after={"verification_status": parent.verification_status.value, "profile_status": profile.status.value},
    )
