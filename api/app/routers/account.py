"""Closing their own account (CLAUDE.md 6.13; phase 10, Reuben 2026-11-23).

Parents and sitters both use these, so they aren't under one role's area; each endpoint checks for itself
(listed in PUBLIC in tests/test_roles.py). Only the signed-in person's own account, never another's.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps import DbSession
from app.models import Profile, Role
from app.routers.complaints import ActivePerson
from app.services import account_status
from app.services import email as email_service

router = APIRouter(prefix="/me", tags=["account"])
Mailer = Annotated[email_service.EmailClient, Depends(email_service.get_email)]


class ClosingOut(BaseModel):
    can_close: bool
    reasons: list[str]  # why not yet
    owed_paise: int  # parents: unpaid charges, to pay first
    pay_due_paise: int  # sitters: still to be paid to her, as usual, after closing


def _closing(db: DbSession, person: Profile) -> ClosingOut:
    found = account_status.closing(db, person, datetime.now(UTC))
    return ClosingOut(
        can_close=not found.blockers,
        reasons=found.blockers,
        owed_paise=found.owed_paise,
        pay_due_paise=found.pay_due_paise,
    )


@router.get("/closing")
def can_i_close(person: ActivePerson, db: DbSession) -> ClosingOut:
    return _closing(db, person)


class CloseIn(BaseModel):
    reason: str | None = Field(default=None, max_length=account_status.REASON_MAX)  # optional, for Pacifyco


class ClosedOut(BaseModel):
    status: str


@router.post("/close")
def close_my_account(body: CloseIn, person: ActivePerson, db: DbSession, mailer: Mailer) -> ClosedOut:
    pay_due = account_status.pay_due(db, person.id) if person.role == Role.sitter else 0
    changed = account_status.close(db, person, body.reason, datetime.now(UTC))
    mailer.send(email_service.account_closed(changed.profile.email, changed.profile.full_name, pay_due))
    return ClosedOut(status=changed.profile.status.value)
