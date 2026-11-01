"""Terms click-wrap (CLAUDE.md 7). Parents accept the parent terms and privacy policy; sitters accept
the Sitter Terms of Use and privacy policy. Each acceptance records the document version, time, IP
address and user agent. When a version changes, people accept again before their next action that
matters (`require_current_terms`, used by booking, buying hours and taking bookings later).

Acceptance goes through `record_acceptances` only, so another signing method (Aadhaar e-sign for sitters,
v2) can be added in one place."""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import AcceptanceMethod, LegalAcceptance, LegalDocument, LegalKind, Profile, Role

REQUIRED: dict[Role, tuple[LegalKind, ...]] = {
    Role.parent: (LegalKind.parent_terms, LegalKind.privacy_policy),
    Role.sitter: (LegalKind.sitter_terms, LegalKind.privacy_policy),
    Role.admin: (),
}
USER_AGENT_MAX = 500


@dataclass(frozen=True)
class Accepted:
    """What the person was shown and agreed to."""

    kind: LegalKind
    version: str


@dataclass(frozen=True)
class RequestInfo:
    ip_address: str | None
    user_agent: str | None


def current_documents(db: Session) -> dict[LegalKind, LegalDocument]:
    """The version in force for each kind: the latest whose effective_at has passed."""
    rows = db.scalars(
        select(LegalDocument).where(LegalDocument.effective_at <= func.now()).order_by(LegalDocument.effective_at)
    )
    return {row.kind: row for row in rows}  # later rows replace earlier ones


def required_documents(db: Session, role: Role) -> list[LegalDocument]:
    current = current_documents(db)
    missing = [kind for kind in REQUIRED[role] if kind not in current]
    if missing:  # a migration seeds every kind; this means the database is out of date
        raise AppError(503, "terms_unavailable", "The terms aren't available right now. Please try again later.")
    return [current[kind] for kind in REQUIRED[role]]


def outstanding(db: Session, profile_id: uuid.UUID, role: Role) -> list[LegalDocument]:
    """Required current documents this person hasn't accepted yet."""
    required = required_documents(db, role)
    accepted = set(
        db.scalars(
            select(LegalAcceptance.document_id).where(
                LegalAcceptance.profile_id == profile_id,
                LegalAcceptance.document_id.in_([doc.id for doc in required]),
            )
        )
    )
    return [doc for doc in required if doc.id not in accepted]


def check_accepted(
    db: Session, role: Role, accepted: list[Accepted], documents: list[LegalDocument] | None = None
) -> list[LegalDocument]:
    """The documents to record, if `accepted` covers each of `documents` (default: everything `role`
    must accept) at its current version. Otherwise 409 (the page showed an older version) or 422
    (something's missing)."""
    required = required_documents(db, role) if documents is None else documents
    given = {item.kind: item.version for item in accepted}
    for doc in required:
        if doc.kind not in given:
            raise AppError(422, "terms_required", "Please agree to the terms and privacy policy to continue")
        if given[doc.kind] != doc.version:
            raise AppError(409, "terms_outdated", "The terms have been updated. Please reload the page and read them.")
    return required


def record_acceptances(
    db: Session, profile_id: uuid.UUID, documents: list[LegalDocument], request: RequestInfo
) -> None:
    """Add click-wrap acceptance rows (a repeat keeps the first). The caller commits."""
    for doc in documents:
        db.execute(
            insert(LegalAcceptance)
            .values(
                profile_id=profile_id,
                document_id=doc.id,
                method=AcceptanceMethod.clickwrap,
                ip_address=request.ip_address,
                user_agent=(request.user_agent or "")[:USER_AGENT_MAX] or None,
            )
            .on_conflict_do_nothing()
        )


def accept_outstanding(db: Session, profile: Profile, accepted: list[Accepted], request: RequestInfo) -> None:
    """Re-acceptance after a version change (or for accounts made before click-wrap existed). Only what's
    outstanding has to be accepted: after a new parent terms version, the privacy policy they already
    accepted isn't asked for again."""
    documents = check_accepted(db, profile.role, accepted, outstanding(db, profile.id, profile.role))
    record_acceptances(db, profile.id, documents, request)
    db.commit()


def require_current_terms(db: Session, profile: Profile) -> None:
    """Call before an action that matters: booking or buying hours (parents), taking bookings (sitters)."""
    if outstanding(db, profile.id, profile.role):
        raise AppError(403, "terms_required", "Please read and accept the updated terms first")
