"""Parental consent (CLAUDE.md 7). Parents accept the current version before uploading any child
documents. The text lives in web/src/content/consent.md; its `version:` line must equal
CONSENT_VERSION (a test checks). Changing the text means a new version, which parents accept again."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Consent

CONSENT_VERSION = "0.1-draft"


def accepted_at(db: Session, parent_id: uuid.UUID, version: str = CONSENT_VERSION) -> datetime | None:
    return db.scalar(select(Consent.accepted_at).where(Consent.parent_id == parent_id, Consent.form_version == version))


def accept(db: Session, parent_id: uuid.UUID, version: str) -> datetime:
    """Record acceptance of `version`, which must be the current one (the text the parent was shown)."""
    if version != CONSENT_VERSION:
        raise AppError(409, "consent_outdated", "The consent form has been updated. Please read the new version.")
    # Accepting again keeps the first record.
    db.execute(insert(Consent).values(parent_id=parent_id, form_version=version).on_conflict_do_nothing())
    db.commit()
    return accepted_at(db, parent_id)


def require_current_consent(db: Session, parent_id: uuid.UUID) -> None:
    """Call before accepting any child document (phase 3)."""
    if accepted_at(db, parent_id) is None:
        raise AppError(403, "consent_required", "Please read and accept the parental consent form first")
