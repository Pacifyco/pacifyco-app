"""The "finish your profile" checklists in each person's area (CLAUDE.md 6.13, decided 2026-11-08).

Sign-up asks only the role and the terms. Everything else is asked for here, and these checklists say
what's left. A parent can't book until theirs is finished (`require_finished_parent_profile`, used by
booking in phase 7). A sitter isn't shown to parents until she's approved and live (`verification.is_live`).
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import (
    Child,
    Document,
    DocumentStatus,
    DocumentType,
    EmergencyContact,
    OnboardingStep,
    Profile,
    PsychAttemptStatus,
    Sitter,
    VerificationStatus,
)
from app.services import accounts, consent, legal, psych_tests, verification

REQUIRED_EMERGENCY_CONTACTS = 1  # per family (CLAUDE.md 7; was two until 2026-11-13)


class ItemStatus(StrEnum):
    to_do = "to_do"  # something for them to fill in or upload
    waiting = "waiting"  # sent; Pacifyco hasn't reviewed it yet
    done = "done"  # filled in (items Pacifyco doesn't review)
    approved = "approved"
    rejected = "rejected"  # reviewed and turned down; they need to fix it


@dataclass(frozen=True)
class Item:
    key: str
    status: ItemStatus
    reason: str | None = None  # when rejected: why, in the admin's words (decided 2026-11-09)
    # The exact next action, e.g. "1 child · certificate needed" or "Add your photo" (UX review 2026-11-13).
    note: str | None = None


def _with_reason(item: Item, reason) -> Item:
    return Item(item.key, item.status, reason(), item.note) if item.status == ItemStatus.rejected else item


def _done(finished: bool) -> ItemStatus:
    return ItemStatus.done if finished else ItemStatus.to_do


def _uploaded(db: Session, owner_id: uuid.UUID, doc_type: DocumentType, child_id: uuid.UUID | None = None) -> bool:
    query = select(Document.id).where(
        Document.owner_profile_id == owner_id,
        Document.type == doc_type,
        Document.status == DocumentStatus.uploaded,
        Document.deleted_at.is_(None),
    )
    if child_id is not None:
        query = query.where(Document.child_id == child_id)
    return db.scalar(query.limit(1)) is not None


# ---------- parents ----------


def _children_reason(db: Session, parent_id: uuid.UUID) -> str | None:
    rejected = db.scalars(
        select(Child).where(Child.parent_id == parent_id, Child.verification_status == VerificationStatus.rejected)
    )
    reasons = [
        f"{child.name}: {child.rejection_reason}" if child.rejection_reason else child.name for child in rejected
    ]
    return "; ".join(reasons) or None


def _children_status(db: Session, parent_id: uuid.UUID) -> ItemStatus:
    """At least one child, each with a birth certificate sent (or already verified, once it's deleted)."""
    children = list(db.scalars(select(Child).where(Child.parent_id == parent_id)))
    if not children:
        return ItemStatus.to_do
    statuses = []
    for child in children:
        if child.verification_status == VerificationStatus.approved:
            statuses.append(ItemStatus.approved)
        elif child.verification_status == VerificationStatus.rejected:
            statuses.append(ItemStatus.rejected)
        elif _uploaded(db, parent_id, DocumentType.birth_certificate, child.id):
            statuses.append(ItemStatus.waiting)
        else:
            statuses.append(ItemStatus.to_do)
    for status in (ItemStatus.rejected, ItemStatus.to_do, ItemStatus.waiting):
        if status in statuses:
            return status
    return ItemStatus.approved


_CHILDREN_NOTE = {
    ItemStatus.to_do: "certificate needed",
    ItemStatus.waiting: "being checked",
    ItemStatus.approved: "verified",
    ItemStatus.rejected: "certificate needs another look",
}


def _children_note(db: Session, parent_id: uuid.UUID, status: ItemStatus) -> str | None:
    """ "1 child · certificate needed", so a parent who has added a child sees what's left."""
    count = db.scalar(select(func.count()).where(Child.parent_id == parent_id)) or 0
    if not count:
        return None
    return f"{count} {'child' if count == 1 else 'children'} · {_CHILDREN_NOTE[status]}"


def parent_checklist(db: Session, profile: Profile) -> list[Item]:
    contacts = db.scalar(select(func.count()).where(EmergencyContact.parent_id == profile.id)) or 0
    children = _children_status(db, profile.id)
    return [
        # Consent comes first: family details can't be saved before it (UX review 2026-11-13). It covers
        # the consents and the current Family Terms and privacy policy, ticked on the same page.
        Item(
            "consent",
            _done(
                consent.summary(db, profile.id).required_accepted
                and not legal.outstanding(db, profile.id, profile.role)
            ),
        ),
        Item("details", _done(accounts.details_complete(profile))),
        _with_reason(
            Item("children", children, note=_children_note(db, profile.id, children)),
            lambda: _children_reason(db, profile.id),
        ),
        Item("emergency_contacts", _done(contacts >= REQUIRED_EMERGENCY_CONTACTS)),
    ]


def parent_profile_finished(items: list[Item]) -> bool:
    """Finished = everything filled in and every birth certificate sent. Children don't have to be
    verified yet: parents can book before that, and the booking waits for it (CLAUDE.md 6.4)."""
    return all(item.status in (ItemStatus.done, ItemStatus.waiting, ItemStatus.approved) for item in items)


def require_finished_parent_profile(db: Session, profile: Profile) -> None:
    """Booking guard (CLAUDE.md 6.4, 6.13); booking (phase 7) calls it."""
    if not parent_profile_finished(parent_checklist(db, profile)):
        raise AppError(409, "profile_unfinished", "Please finish your profile before booking")


# ---------- sitters ----------


def _reviewed(review: VerificationStatus, sent: bool) -> ItemStatus:
    if review == VerificationStatus.approved:
        return ItemStatus.approved
    if review == VerificationStatus.rejected:
        return ItemStatus.rejected
    return ItemStatus.waiting if sent else ItemStatus.to_do


def sitter_checklist(db: Session, profile: Profile, sitter: Sitter) -> list[Item]:
    """Her eight onboarding steps, in the order she does them (Reuben, 2026-11-13): sitter consent, her
    details, about you, ID verification, health disclosure, references, payment details and the
    psychology screening. The web app opens each only once the ones before it are filled in."""
    reviews = verification.step_statuses(db, sitter.profile_id)
    step_reasons = {
        row.step.value: row.rejection_reason
        for row in db.scalars(select(OnboardingStep).where(OnboardingStep.sitter_id == sitter.profile_id))
    }
    rejected_references = [
        f"{ref.name}: {ref.rejection_reason}" if ref.rejection_reason else ref.name
        for ref in verification.sitter_references(db, sitter.profile_id)
        if ref.outcome == VerificationStatus.rejected
    ]
    step_reasons["references"] = "; ".join(rejected_references) or None
    references = len(verification.sitter_references(db, sitter.profile_id))
    attempt = psych_tests.latest_attempt(db, sitter.profile_id)
    step_reasons["psych_test"] = attempt.rejection_reason if attempt is not None else None

    # About you: everything parents see about her, all required, with the exact thing still missing.
    missing = [
        note
        for note, given in (
            (
                "Add your date of birth, experience and a few words about you",
                sitter.date_of_birth and sitter.bio and sitter.years_experience is not None,
            ),
            ("Choose the ages you care for and the languages you speak", sitter.age_groups and sitter.languages),
            ("Add your photo", _uploaded(db, profile.id, DocumentType.photo)),
        )
        if not given
    ]
    # ID verification: both IDs, and her first-aid certificate if she says she has one. The police
    # certificate can come later, but Pacifyco needs it before her profile goes live.
    ids_sent = (
        _uploaded(db, profile.id, DocumentType.government_id)
        and _uploaded(db, profile.id, DocumentType.college_or_work_id)
        and (not sitter.first_aid or _uploaded(db, profile.id, DocumentType.first_aid_certificate))
    )
    ids = _reviewed(reviews["identity_documents"], ids_sent)
    police = reviews["police_certificate"]
    if police == VerificationStatus.rejected:
        ids, step_reasons["identity_documents"] = ItemStatus.rejected, step_reasons.get("police_certificate")
    elif ids == ItemStatus.approved and police != VerificationStatus.approved:
        ids = ItemStatus.waiting  # her IDs are fine; the police certificate is still to come or be checked
    ids_note = (
        None
        if _uploaded(db, profile.id, DocumentType.police_certificate) or police == VerificationStatus.approved
        else "Your police clearance certificate is still needed before your profile goes live"
    )

    items = [
        # The sitter consent, Sitter Terms of Use and privacy policy, on one page (decided 2026-11-12).
        Item("consent", _done(not legal.outstanding(db, profile.id, profile.role))),
        Item("details", _done(accounts.details_complete(profile))),
        Item("profile", _reviewed(reviews["profile"], not missing), note=missing[0] if missing else None),
        Item("identity_documents", ids, note=ids_note if ids != ItemStatus.to_do else None),
        # Optional to fill in, but she confirms it (saving it empty means "nothing to declare").
        Item("health_disclosure", _done(sitter.health_disclosure_confirmed_at is not None)),
        Item("references", _reviewed(reviews["references"], references >= verification.REQUIRED_REFERENCES)),
        Item("payout", _done(sitter.payout_method is not None)),
        Item(
            "psych_test",
            _reviewed(reviews["psych_test"], attempt is not None and attempt.status == PsychAttemptStatus.submitted),
        ),
    ]
    return [_with_reason(item, lambda key=item.key: step_reasons.get(key)) for item in items]
