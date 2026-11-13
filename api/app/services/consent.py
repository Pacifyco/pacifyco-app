"""Parental consent (CLAUDE.md section 7, following Family Terms 11.2): four things ticked
separately, plus an optional, withdrawable marketing consent. The same page has the tick for the
Family Terms of Use and privacy policy (moved there from sign-up, decided 2026-11-12); those are
recorded by `legal`. The text lives in web/src/content/consent.md; its `version:` line must equal
CONSENT_VERSION (a test checks)."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Consent, ConsentKind, Parent, Role
from app.services import legal

CONSENT_VERSION = "0.2-draft"

REQUIRED_KINDS = (
    ConsentKind.own_data,
    ConsentKind.child_data,
    ConsentKind.share_care_details,
    ConsentKind.emergency_authorisation,
)


@dataclass(frozen=True)
class ConsentSummary:
    version: str
    required_accepted: bool  # every required kind given, at the current version
    accepted_at: datetime | None  # when the last of them was given, if all are
    marketing: bool  # current opt-in state


def _latest(db: Session, parent_id: uuid.UUID, kind: ConsentKind, version: str = CONSENT_VERSION) -> Consent | None:
    return db.scalar(
        select(Consent)
        .where(Consent.parent_id == parent_id, Consent.kind == kind, Consent.version == version)
        .order_by(Consent.created_at.desc())
        .limit(1)
    )


def _given(db: Session, parent_id: uuid.UUID, kind: ConsentKind) -> bool:
    row = _latest(db, parent_id, kind)
    return bool(row and row.accepted)


def summary(db: Session, parent_id: uuid.UUID) -> ConsentSummary:
    given = [_latest(db, parent_id, kind) for kind in REQUIRED_KINDS]
    required_accepted = all(row is not None for row in given)
    accepted_at = max((row.created_at for row in given if row), default=None) if required_accepted else None
    return ConsentSummary(
        version=CONSENT_VERSION,
        required_accepted=required_accepted,
        accepted_at=accepted_at,
        marketing=_given(db, parent_id, ConsentKind.marketing),
    )


def _set_toggle(db: Session, parent_id: uuid.UUID, kind: ConsentKind, accepted: bool) -> ConsentSummary:
    """A toggle that's withdrawable both ways. No row yet means "not given", so this only adds a row
    when the choice actually changes -- saying no when there's nothing to withdraw changes nothing,
    same as never ticking the box in the first place."""
    if _given(db, parent_id, kind) != accepted:
        db.add(Consent(parent_id=parent_id, kind=kind, version=CONSENT_VERSION, accepted=accepted))
        db.commit()
    return summary(db, parent_id)


def set_marketing(db: Session, parent_id: uuid.UUID, accepted: bool) -> ConsentSummary:
    """Opt in or withdraw (CLAUDE.md 7: marketing consent is withdrawable)."""
    return _set_toggle(db, parent_id, ConsentKind.marketing, accepted)


def accept(
    db: Session,
    parent_id: uuid.UUID,
    version: str,
    marketing: bool,
    terms: list[legal.Accepted],
    request: legal.RequestInfo,
) -> ConsentSummary:
    """Record every required consent at `version`, which must be current, plus the marketing choice,
    and the terms and privacy policy the parent still has to accept (`terms`: the versions they were
    shown), all or nothing. Calling this at all means every required box was ticked (the web only
    allows it once they are); repeating it keeps the first acceptance of each."""
    if version != CONSENT_VERSION:
        raise AppError(409, "consent_outdated", "The consent form has been updated. Please read the new version.")
    if db.get(Parent, parent_id) is None:  # a parent profile without its parent record: edited outside the app
        raise AppError(409, "account_incomplete", "Your account isn't fully set up. Please contact Pacifyco.")
    documents = legal.check_accepted(db, Role.parent, terms, legal.outstanding(db, parent_id, Role.parent))

    for kind in REQUIRED_KINDS:
        if _latest(db, parent_id, kind) is None:
            db.add(Consent(parent_id=parent_id, kind=kind, version=version, accepted=True))
    legal.record_acceptances(db, parent_id, documents, request)
    db.commit()  # commit the required kinds now: set_marketing only commits when the choice changes
    return set_marketing(db, parent_id, marketing)


def require_current_consent(db: Session, parent_id: uuid.UUID) -> None:
    """Call before any child-linked document (CLAUDE.md 9, "Consent"): every required kind at the
    current version."""
    for kind in REQUIRED_KINDS:
        if _latest(db, parent_id, kind) is None:
            raise AppError(403, "consent_required", "Please read and accept the parental consent form first")
