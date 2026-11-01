"""The parent area. Every route here is for parents only (CLAUDE.md 9: wrong role gets 403)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import require_role
from app.deps import DbSession
from app.models import Profile, Role
from app.services import consent

router = APIRouter(prefix="/parent", tags=["parent"], dependencies=[Depends(require_role(Role.parent))])
Parent = Annotated[Profile, Depends(require_role(Role.parent))]


class ConsentStatus(BaseModel):
    version: str  # the current version
    accepted_at: datetime | None  # when this parent accepted it, if they have


class AcceptConsent(BaseModel):
    version: str  # the version the parent was shown


@router.get("/consent")
def get_consent(parent: Parent, db: DbSession) -> ConsentStatus:
    return ConsentStatus(version=consent.CONSENT_VERSION, accepted_at=consent.accepted_at(db, parent.id))


@router.post("/consent")
def accept_consent(body: AcceptConsent, parent: Parent, db: DbSession) -> ConsentStatus:
    return ConsentStatus(version=consent.CONSENT_VERSION, accepted_at=consent.accept(db, parent.id, body.version))
