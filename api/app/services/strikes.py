"""Strikes (CLAUDE.md 6.6; phase 7 "Strikes").

- A strike blocks the sitter from new bookings for: 1st 24 hours, 2nd 3 days, 3rd 1 week, 4th 2 weeks;
  the 5th is permanent removal.
- Only strikes given in the last 6 months count; each expires 6 months after it was given.
- Existing confirmed bookings stay unless an admin cancels them.
- Admins can add or remove a strike with a reason (audit logged). A sitter who cancelled late because
  she was ill can upload a doctor's note for an admin to look at (6.5).

The block is worked out whenever a strike is given or removed and kept on the sitter
(`sitters.blocked_until`), so finding and booking her stays a simple query. A strike older than 6 months
stops counting by its date, so no job has to expire it.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import (
    AccountAction,
    AccountActionKind,
    AccountActionRow,
    Document,
    DocumentStatus,
    DocumentType,
    Profile,
    ProfileStatus,
    Sitter,
    Strike,
    StrikeReason,
)
from app.services import audit

COUNTS_FOR = timedelta(days=182)  # 6 months (6.6)
LADDER = {1: timedelta(hours=24), 2: timedelta(days=3), 3: timedelta(weeks=1), 4: timedelta(weeks=2)}
REMOVED_AT = 5  # the 5th strike is permanent removal


def counting(db: Session, sitter_id: uuid.UUID, now: datetime) -> list[Strike]:
    """Her strikes that count: not removed and given in the last 6 months, oldest first."""
    return list(
        db.scalars(
            select(Strike)
            .where(Strike.sitter_id == sitter_id, Strike.removed_at.is_(None), Strike.given_at > now - COUNTS_FOR)
            .order_by(Strike.given_at)
        )
    )


def block_for(strikes: list[Strike]) -> datetime | None:
    """When the block from these strikes ends: each one blocks from when it was given, for its place on
    the ladder (counting only strikes from the 6 months before it). The latest end wins."""
    until = None
    for index, strike in enumerate(strikes):
        place = sum(1 for earlier in strikes[: index + 1] if earlier.given_at > strike.given_at - COUNTS_FOR)
        if place >= REMOVED_AT:
            continue  # removal, handled apart
        end = strike.given_at + LADDER[place]
        until = end if until is None or end > until else until
    return until


@dataclass(frozen=True)
class Outcome:
    strike: Strike
    blocked_until: datetime | None
    removed: bool  # the 5th strike: her account was removed


def _recalculate(
    db: Session, actor_id: uuid.UUID | None, sitter_id: uuid.UUID, now: datetime
) -> tuple[datetime | None, bool]:
    sitter = db.scalar(select(Sitter).where(Sitter.profile_id == sitter_id).with_for_update())
    if sitter is None:
        raise AppError(404, "not_found", "That sitter doesn't exist")
    strikes = counting(db, sitter_id, now)
    sitter.blocked_until = block_for(strikes)
    removed = False
    if len(strikes) >= REMOVED_AT:
        profile = db.get(Profile, sitter_id)
        assert profile is not None
        if profile.status != ProfileStatus.removed:
            audit.record(
                db,
                actor_id,
                "sitter_removed",
                "profiles",
                str(sitter_id),
                before={"status": profile.status.value},
                after={"status": ProfileStatus.removed.value, "reason": "fifth_strike"},
            )
            profile.status = ProfileStatus.removed
            db.add(
                AccountActionRow(
                    profile_id=sitter_id,
                    action=AccountAction.removed,
                    kind=AccountActionKind.strikes,
                    reason="Five strikes in 6 months.",
                    admin_id=actor_id,
                )
            )
            removed = True
    return sitter.blocked_until, removed


def give(
    db: Session,
    actor_id: uuid.UUID | None,
    sitter_id: uuid.UUID,
    reason: StrikeReason,
    now: datetime,
    booking_id: uuid.UUID | None = None,
    note: str | None = None,
) -> Outcome:
    """Adds a strike and works out her block (or removal). The caller commits."""
    strike = Strike(
        sitter_id=sitter_id,
        booking_id=booking_id,
        reason=reason,
        note=note,
        given_at=now,
        expires_at=now + COUNTS_FOR,
    )
    db.add(strike)
    db.flush()
    audit.record(
        db,
        actor_id,  # None when the rules gave it
        "strike_given",
        "strike",
        str(strike.id),
        after={
            "sitter_id": str(sitter_id),
            "booking_id": str(booking_id) if booking_id else None,
            "reason": reason.value,
        },
    )
    blocked_until, removed = _recalculate(db, actor_id, sitter_id, now)
    return Outcome(strike, blocked_until, removed)


def remove(db: Session, admin_id: uuid.UUID, strike_id: uuid.UUID, reason: str, now: datetime) -> Outcome:
    """An admin removes a strike with a reason (for example, a doctor's note). It's kept, marked removed.
    Her block is worked out again; a removed account isn't brought back here (an admin decides that)."""
    strike = db.scalar(select(Strike).where(Strike.id == strike_id).with_for_update())
    if strike is None:
        raise AppError(404, "not_found", "That strike doesn't exist")
    if strike.removed_at is not None:
        raise AppError(409, "already_removed", "This strike has already been removed.")
    strike.removed_by = admin_id
    strike.removed_at = now
    strike.removal_reason = reason
    audit.record(
        db,
        admin_id,
        "strike_removed",
        "strike",
        str(strike.id),
        before={"removed": False},
        after={"removed": True, "reason": reason},
    )
    db.flush()
    blocked_until, _ = _recalculate(db, admin_id, strike.sitter_id, now)
    db.commit()
    return Outcome(strike, blocked_until, False)


def attach_doctor_note(db: Session, sitter_id: uuid.UUID, strike_id: uuid.UUID, document_id: uuid.UUID) -> Strike:
    """She sends a doctor's note for a late cancellation, for an admin to look at (6.5)."""
    strike = db.scalar(select(Strike).where(Strike.id == strike_id, Strike.sitter_id == sitter_id).with_for_update())
    if strike is None:
        raise AppError(404, "not_found", "That strike doesn't exist")
    if strike.reason != StrikeReason.late_cancellation:
        raise AppError(409, "not_a_late_cancellation", "A doctor's note is for a late cancellation.")
    if strike.removed_at is not None:
        raise AppError(409, "already_removed", "This strike has already been removed.")
    document = db.get(Document, document_id)
    if (
        document is None
        or document.owner_profile_id != sitter_id
        or document.type != DocumentType.doctor_note
        or document.status != DocumentStatus.uploaded
    ):
        raise AppError(422, "doctor_note_needed", "Please upload your doctor's note first.")
    strike.doctor_note_document_id = document.id
    audit.record(
        db,
        sitter_id,
        "doctor_note_sent",
        "strike",
        str(strike.id),
        after={"document_id": str(document.id)},
    )
    db.commit()
    return strike


def is_blocked(db: Session, sitter_id: uuid.UUID, now: datetime) -> bool:
    until = db.scalar(select(Sitter.blocked_until).where(Sitter.profile_id == sitter_id))
    return until is not None and until > now


def for_sitter(db: Session, sitter_id: uuid.UUID) -> list[Strike]:
    """All her strikes, newest first (removed and expired ones too)."""
    return list(db.scalars(select(Strike).where(Strike.sitter_id == sitter_id).order_by(Strike.given_at.desc())))
