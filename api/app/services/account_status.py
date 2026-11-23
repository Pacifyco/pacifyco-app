"""Suspending, removing and reinstating parents and sitters (phase 10 "User management"; Reuben, 2026-11-22).

- An admin suspends or removes an account with a kind of reason (low ratings, safety or conduct, strikes,
  other) and the reason itself; the person is emailed the reason and how to appeal.
- **A removal (or suspension) for low ratings waits** until she's been told the reason on her rating flag and
  has responded, or her 12 hours have passed (6.11). The other kinds don't wait, so a theft is handled at once.
- **Upcoming bookings are cancelled and refunded** (`cancelled_by_admin`, no strike): every booking of theirs
  that hasn't started (a request, one waiting for payment, or a paid one). The other side is emailed; for a
  sitter, the admins too, to find the families another sitter. Bookings under way are left for an admin.
- **Reinstating** makes a suspended or removed account usable again: `active` if the family is verified or
  the sitter approved, otherwise back to `pending`. Refused for a sitter with 5 strikes still counting
  (remove a strike first, or the rules would remove her again).
- Each change is a row in `account_actions` and an audit row. The automatic ones (a 5th strike, a parent's
  theft or abuse report, and reinstating from an incident) are recorded there too, by no one or the admin.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import (
    AccountAction,
    AccountActionKind,
    AccountActionRow,
    Booking,
    BookingStatus,
    OnboardingStatus,
    Parent,
    Payment,
    Profile,
    ProfileStatus,
    RatingFlag,
    Role,
    Sitter,
    VerificationStatus,
)
from app.services import admin_bookings, audit, reviews, strikes

# Bookings cancelled with the account: everything that hasn't started yet.
UPCOMING = (
    BookingStatus.requested,
    BookingStatus.pending_payment,
    BookingStatus.awaiting_verification,
    BookingStatus.confirmed,
)
REASON_MAX = 1000


@dataclass(frozen=True)
class Changed:
    profile: Profile
    row: AccountActionRow
    cancelled: list[Booking] = field(default_factory=list)
    refunds: list[Payment] = field(default_factory=list)


def record(
    db: Session,
    admin_id: uuid.UUID | None,
    profile: Profile,
    action: AccountAction,
    kind: AccountActionKind | None,
    reason: str,
) -> AccountActionRow:
    """A row in the account's history. The caller changes the status and commits."""
    row = AccountActionRow(profile_id=profile.id, action=action, kind=kind, reason=reason, admin_id=admin_id)
    db.add(row)
    db.flush()
    return row


def history(db: Session, profile_id: uuid.UUID) -> list[AccountActionRow]:
    """Newest first."""
    return list(
        db.scalars(
            select(AccountActionRow)
            .where(AccountActionRow.profile_id == profile_id)
            .order_by(AccountActionRow.created_at.desc(), AccountActionRow.id)
        )
    )


def _person(db: Session, profile_id: uuid.UUID) -> Profile:
    profile = db.scalar(select(Profile).where(Profile.id == profile_id).with_for_update())
    if profile is None or profile.role not in (Role.parent, Role.sitter):
        raise AppError(404, "not_found", "We couldn't find that person.")
    return profile


def _reason(reason: str) -> str:
    cleaned = reason.strip()
    if not cleaned:
        raise AppError(422, "reason_required", "Please give a reason. The person will see it.")
    if len(cleaned) > REASON_MAX:
        raise AppError(422, "reason_too_long", f"Please keep the reason under {REASON_MAX} characters.")
    return cleaned


def last_told_flag(db: Session, sitter_id: uuid.UUID) -> RatingFlag | None:
    """Her most recent rating flag that an admin told her about."""
    return db.scalar(
        select(RatingFlag)
        .where(RatingFlag.sitter_id == sitter_id, RatingFlag.told_at.is_not(None))
        .order_by(RatingFlag.told_at.desc())
        .limit(1)
    )


def ratings_wait(db: Session, profile: Profile, now: datetime) -> str | None:
    """Why she can't yet be suspended or removed for low ratings (6.11), or None if she can."""
    if profile.role != Role.sitter:
        return "Only a sitter can be suspended or removed for low ratings."
    in_progress = reviews.current_flag(db, profile.id)
    if in_progress is not None and in_progress.told_at is None:
        return "Tell her the reason on Ratings first. She then has 12 hours to respond."
    flag = in_progress or last_told_flag(db, profile.id)
    if flag is None:
        return "She has no low-rating flag. Choose another kind of reason."
    if not reviews.can_decide(flag, now):
        return "She has 12 hours from being told to respond. Please wait for her response or the end of those hours."
    return None


def _cancel_upcoming(
    db: Session, admin_id: uuid.UUID, profile: Profile, action: AccountAction, now: datetime
) -> tuple[list[Booking], list[Payment]]:
    found = list(
        db.scalars(
            select(Booking)
            .where(
                or_(Booking.parent_id == profile.id, Booking.sitter_id == profile.id),
                Booking.status.in_(UPCOMING),
                Booking.starts_at > now,
            )
            .order_by(Booking.starts_at)
            .with_for_update()
        )
    )
    refunds: list[Payment] = []
    for booking in found:
        why = {"account": str(profile.id), "why": action.value}
        refunds.extend(admin_bookings.cancel_by_admin(db, admin_id, booking, why))
    return found, refunds


def _block(
    db: Session,
    admin_id: uuid.UUID,
    profile_id: uuid.UUID,
    action: AccountAction,
    kind: AccountActionKind,
    reason: str,
    now: datetime,
) -> Changed:
    profile = _person(db, profile_id)
    reason = _reason(reason)
    if action == AccountAction.suspended and profile.status in (ProfileStatus.suspended, ProfileStatus.removed):
        raise AppError(409, "already_blocked", "This account is already suspended or removed.")
    if action == AccountAction.removed and profile.status == ProfileStatus.removed:
        raise AppError(409, "already_removed", "This account has already been removed.")
    if kind == AccountActionKind.low_ratings:
        wait = ratings_wait(db, profile, now)
        if wait is not None:
            raise AppError(409, "ratings_not_decidable", wait)
    status = ProfileStatus.suspended if action == AccountAction.suspended else ProfileStatus.removed
    audit.record(
        db,
        admin_id,
        f"account_{action.value}",
        "profiles",
        str(profile.id),
        before={"status": profile.status.value},
        after={"status": status.value, "kind": kind.value, "reason": reason},
    )
    profile.status = status
    row = record(db, admin_id, profile, action, kind, reason)
    cancelled, refunds = _cancel_upcoming(db, admin_id, profile, action, now)
    db.commit()
    return Changed(profile, row, cancelled, refunds)


def suspend(
    db: Session, admin_id: uuid.UUID, profile_id: uuid.UUID, kind: AccountActionKind, reason: str, now: datetime
) -> Changed:
    return _block(db, admin_id, profile_id, AccountAction.suspended, kind, reason, now)


def remove(
    db: Session, admin_id: uuid.UUID, profile_id: uuid.UUID, kind: AccountActionKind, reason: str, now: datetime
) -> Changed:
    return _block(db, admin_id, profile_id, AccountAction.removed, kind, reason, now)


def status_when_reinstated(db: Session, profile: Profile) -> ProfileStatus:
    """Active once the family is verified or the sitter approved; otherwise pending, as before."""
    if profile.role == Role.parent:
        verified = db.scalar(select(Parent.verification_status).where(Parent.profile_id == profile.id))
        return ProfileStatus.active if verified == VerificationStatus.approved else ProfileStatus.pending
    approved = db.scalar(select(Sitter.onboarding_status).where(Sitter.profile_id == profile.id))
    return ProfileStatus.active if approved == OnboardingStatus.approved else ProfileStatus.pending


def five_strikes(db: Session, profile: Profile, now: datetime) -> bool:
    return profile.role == Role.sitter and len(strikes.counting(db, profile.id, now)) >= strikes.REMOVED_AT


def reinstate(db: Session, admin_id: uuid.UUID, profile_id: uuid.UUID, reason: str, now: datetime) -> Changed:
    profile = _person(db, profile_id)
    reason = _reason(reason)
    if profile.status not in (ProfileStatus.suspended, ProfileStatus.removed):
        raise AppError(409, "not_blocked", "This account isn't suspended or removed.")
    if five_strikes(db, profile, now):
        raise AppError(
            409, "five_strikes", "She still has 5 strikes counting. Remove a strike first, or she'd be removed again."
        )
    status = status_when_reinstated(db, profile)
    audit.record(
        db,
        admin_id,
        "account_reinstated",
        "profiles",
        str(profile.id),
        before={"status": profile.status.value},
        after={"status": status.value, "reason": reason},
    )
    profile.status = status
    row = record(db, admin_id, profile, AccountAction.reinstated, None, reason)
    db.commit()
    return Changed(profile, row)


def upcoming_count(db: Session, profile_id: uuid.UUID, now: datetime) -> int:
    """Bookings a suspension or removal would cancel."""
    return len(
        db.scalars(
            select(Booking.id).where(
                or_(Booking.parent_id == profile_id, Booking.sitter_id == profile_id),
                Booking.status.in_(UPCOMING),
                Booking.starts_at > now,
            )
        ).all()
    )


def under_way_count(db: Session, profile_id: uuid.UUID, now: datetime) -> int:
    """Bookings already started and not finished, which stay for an admin to handle."""
    return len(
        db.scalars(
            select(Booking.id).where(
                or_(Booking.parent_id == profile_id, Booking.sitter_id == profile_id),
                or_(
                    Booking.status == BookingStatus.in_progress,
                    (Booking.status == BookingStatus.confirmed) & (Booking.starts_at <= now),
                ),
            )
        ).all()
    )
