"""Parental consent (CLAUDE.md section 7, following Family Terms 11.2): four things ticked
separately at sign-up, plus an optional, withdrawable marketing consent, plus a single-parent
declaration used later on the masked-Aadhaar upload screen. The text lives in
web/src/content/consent.md; its `version:` line must equal CONSENT_VERSION (a test checks)."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Consent, ConsentKind, Parent

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


def summary(db: Session, parent_id: uuid.UUID) -> ConsentSummary:
    given = [_latest(db, parent_id, kind) for kind in REQUIRED_KINDS]
    required_accepted = all(row is not None for row in given)
    accepted_at = max((row.created_at for row in given if row), default=None) if required_accepted else None
    marketing_row = _latest(db, parent_id, ConsentKind.marketing)
    return ConsentSummary(
        version=CONSENT_VERSION,
        required_accepted=required_accepted,
        accepted_at=accepted_at,
        marketing=bool(marketing_row and marketing_row.accepted),
    )


def set_marketing(db: Session, parent_id: uuid.UUID, accepted: bool) -> ConsentSummary:
    """Opt in or withdraw (CLAUDE.md 7: marketing consent is withdrawable). No row yet means "not
    opted in", so this only adds a row when the choice actually changes -- saying no when there is
    nothing to withdraw changes nothing, same as never ticking the box at sign-up."""
    current = _latest(db, parent_id, ConsentKind.marketing)
    effective = current.accepted if current else False
    if effective != accepted:
        db.add(Consent(parent_id=parent_id, kind=ConsentKind.marketing, version=CONSENT_VERSION, accepted=accepted))
        db.commit()
    return summary(db, parent_id)


def accept(db: Session, parent_id: uuid.UUID, version: str, marketing: bool) -> ConsentSummary:
    """Record every required consent at `version`, which must be current, plus the marketing choice.
    Calling this at all means every required box was ticked (the web only allows it once they are);
    repeating it keeps the first acceptance of each required kind."""
    if version != CONSENT_VERSION:
        raise AppError(409, "consent_outdated", "The consent form has been updated. Please read the new version.")
    if db.get(Parent, parent_id) is None:  # a parent profile without its parent record: edited outside the app
        raise AppError(409, "account_incomplete", "Your account isn't fully set up. Please contact Pacify.")

    for kind in REQUIRED_KINDS:
        if _latest(db, parent_id, kind) is None:
            db.add(Consent(parent_id=parent_id, kind=kind, version=version, accepted=True))
    db.flush()
    return set_marketing(db, parent_id, marketing)


def require_current_consent(db: Session, parent_id: uuid.UUID) -> None:
    """Call before any child-linked document (CLAUDE.md 9, "Consent"): every required kind at the
    current version."""
    for kind in REQUIRED_KINDS:
        if _latest(db, parent_id, kind) is None:
            raise AppError(403, "consent_required", "Please read and accept the parental consent form first")
