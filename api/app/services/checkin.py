"""Check-in and check-out codes (CLAUDE.md 6.7; phase 8).

Each booking gets a 4-digit check-in code, and, once she's checked in, a 4-digit check-out code. A code
is generated the first time the parent asks to see it and kept encrypted at rest (never in plain text);
asking again just decrypts and returns the same one, so nothing is weakened by viewing it more than once.
The parent reads it out to the sitter, who enters it in her app, along with her location (if she allows
it; if not, that's recorded by leaving the location columns empty and check-in still goes ahead). Five
wrong codes locks the booking's codes and alerts admins.

Check-in moves the booking to `in_progress`; check-out moves it to `completed`. Overtime and sitter pay
from hours worked are worked out elsewhere, once those phase 8/9 items exist.

A booking needs an admin's attention (`needing_attention`) when it's still `in_progress` 30+ minutes past
its end (an overdue check-out), or its codes are locked -- either way, there's no other way for it to
move on. Admins are emailed once about an overdue check-out (`alert_overdue_checkouts`, the frequent job);
a locked booking was already emailed about when it locked (`routers/sitters.py`). An admin calls both
people and can close the booking by hand with a reason (`close_by_admin`), which an overdue check-out and
a locked one both need the same way.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import String, and_, cast, exists, or_, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import AuditLog, Booking, BookingStatus
from app.services import audit, encryption
from app.services import overtime as overtime_service
from app.services.availability import INDIA, today_in_india
from app.services.overtime import Charged

MAX_ATTEMPTS = 5  # 6.7: lock after 5 wrong attempts
OVERDUE_AFTER = timedelta(minutes=30)  # 6.7: an alert once a booking is this late to check out
OVERDUE_ALERTED = "overdue_checkout_alerted"
NEEDS_ATTENTION = (BookingStatus.confirmed, BookingStatus.in_progress)


def _generate() -> str:
    return f"{secrets.randbelow(10_000):04d}"


def _locked_booking(db: Session, booking_id: uuid.UUID, **owner: uuid.UUID) -> Booking:
    query = select(Booking).where(Booking.id == booking_id)
    for column, value in owner.items():
        query = query.where(getattr(Booking, column) == value)
    booking = db.scalar(query.with_for_update())
    if booking is None:
        raise AppError(404, "not_found", "We couldn't find that booking.")
    return booking


def check_in_code(db: Session, parent_id: uuid.UUID, booking_id: uuid.UUID, key: str, now: datetime) -> str:
    """Shown only on the day of the booking, while it's confirmed and not yet checked in (6.7)."""
    booking = _locked_booking(db, booking_id, parent_id=parent_id)
    if booking.status != BookingStatus.confirmed:
        raise AppError(409, "not_now", "This booking's check-in code isn't ready.")
    if today_in_india(now) != booking.starts_at.astimezone(INDIA).date():
        raise AppError(409, "too_early", "The check-in code shows on the day of the booking.")
    if booking.check_in_code_encrypted is None:
        booking.check_in_code_encrypted = encryption.encrypt(key, _generate())
        db.commit()
    return encryption.decrypt(key, booking.check_in_code_encrypted)


def check_out_code(db: Session, parent_id: uuid.UUID, booking_id: uuid.UUID, key: str) -> str:
    """Appears only once she's checked in (6.7)."""
    booking = _locked_booking(db, booking_id, parent_id=parent_id)
    if booking.status != BookingStatus.in_progress:
        raise AppError(409, "not_now", "This booking's check-out code isn't ready.")
    if booking.check_out_code_encrypted is None:
        booking.check_out_code_encrypted = encryption.encrypt(key, _generate())
        db.commit()
    return encryption.decrypt(key, booking.check_out_code_encrypted)


@dataclass(frozen=True)
class Checked:
    booking: Booking
    overtime: Charged | None = None


def _check_code(
    db: Session, booking: Booking, encrypted: bytes | None, code: str, key: str, actor_id: uuid.UUID
) -> None:
    """Wrong: counts the attempt (locking and raising `codes_locked` on the 5th) and raises `wrong_code`
    otherwise. Right: does nothing (the caller applies the state change)."""
    if booking.codes_locked:
        raise AppError(409, "codes_locked", "Too many wrong codes were entered. Pacifyco has been told.")
    if encrypted is not None and encryption.decrypt(key, encrypted) == code:
        return
    booking.code_attempts += 1
    locked_now = booking.code_attempts >= MAX_ATTEMPTS
    if locked_now:
        booking.codes_locked = True
    audit.record(
        db,
        actor_id,
        "code_entry_failed",
        "booking",
        str(booking.id),
        after={"attempts": booking.code_attempts, "locked": locked_now},
    )
    db.commit()
    if locked_now:
        raise AppError(409, "codes_locked", "Too many wrong codes were entered. Pacifyco has been told.")
    raise AppError(
        409,
        "wrong_code",
        "That code's wrong.",
        {"attempts_left": MAX_ATTEMPTS - booking.code_attempts},
    )


def check_in(
    db: Session,
    sitter_id: uuid.UUID,
    booking_id: uuid.UUID,
    code: str,
    lat: float | None,
    lng: float | None,
    key: str,
    now: datetime,
) -> Checked:
    booking = _locked_booking(db, booking_id, sitter_id=sitter_id)
    if booking.status != BookingStatus.confirmed:
        raise AppError(409, "not_now", "This booking can't be checked into now.")
    _check_code(db, booking, booking.check_in_code_encrypted, code, key, sitter_id)
    booking.checked_in_at = now
    booking.check_in_lat = lat
    booking.check_in_lng = lng
    booking.code_attempts = 0  # a fresh count for the check-out code
    booking.status = BookingStatus.in_progress
    audit.record(db, sitter_id, "checked_in", "booking", str(booking.id), after={"status": "in_progress"})
    db.commit()
    return Checked(booking)


def check_out(
    db: Session,
    sitter_id: uuid.UUID,
    booking_id: uuid.UUID,
    code: str,
    lat: float | None,
    lng: float | None,
    key: str,
    now: datetime,
) -> Checked:
    booking = _locked_booking(db, booking_id, sitter_id=sitter_id)
    if booking.status != BookingStatus.in_progress:
        raise AppError(409, "not_now", "This booking can't be checked out of now.")
    _check_code(db, booking, booking.check_out_code_encrypted, code, key, sitter_id)
    booking.checked_out_at = now
    booking.check_out_lat = lat
    booking.check_out_lng = lng
    booking.status = BookingStatus.completed
    audit.record(db, sitter_id, "checked_out", "booking", str(booking.id), after={"status": "completed"})
    charged = overtime_service.charge_for_checkout(db, booking, now)
    db.commit()
    return Checked(booking, charged)


def is_overdue(booking: Booking, now: datetime) -> bool:
    return booking.status == BookingStatus.in_progress and booking.ends_at + OVERDUE_AFTER <= now


@dataclass(frozen=True)
class NeedsAttention:
    booking: Booking
    overdue: bool  # otherwise it's here because its codes are locked


def needing_attention(db: Session, now: datetime) -> list[NeedsAttention]:
    """Bookings an admin should call about and may need to close by hand (6.7): still in progress 30+
    minutes past the end, or their codes locked with no other way through. Oldest start first."""
    rows = db.scalars(
        select(Booking)
        .where(
            Booking.status.in_(NEEDS_ATTENTION),
            or_(
                Booking.codes_locked.is_(True),
                and_(Booking.status == BookingStatus.in_progress, Booking.ends_at + OVERDUE_AFTER <= now),
            ),
        )
        .order_by(Booking.starts_at)
    ).all()
    return [NeedsAttention(booking, is_overdue(booking, now)) for booking in rows]


def overdue_not_alerted(db: Session, now: datetime) -> list[Booking]:
    """Overdue check-outs admins haven't been emailed about yet (6.7)."""
    alerted = exists().where(
        AuditLog.action == OVERDUE_ALERTED, AuditLog.entity == "booking", AuditLog.entity_id == cast(Booking.id, String)
    )
    return list(
        db.scalars(
            select(Booking).where(
                Booking.status == BookingStatus.in_progress, Booking.ends_at + OVERDUE_AFTER <= now, ~alerted
            )
        )
    )


def mark_overdue_alerted(db: Session, overdue: list[Booking]) -> None:
    """Remembers each alert (in the audit log), so no booking is alerted twice. The caller commits."""
    for booking in overdue:
        audit.record(db, None, OVERDUE_ALERTED, "booking", str(booking.id), after={})


def close_by_admin(db: Session, admin_id: uuid.UUID, booking_id: uuid.UUID, reason: str, now: datetime) -> Booking:
    """An admin closes a booking by hand after calling both people (6.7): an overdue check-out, or codes
    locked with no other way through. If she checked in but never checked out, this stands in for that
    timestamp; if she never checked in at all, it's left empty too."""
    booking = _locked_booking(db, booking_id)
    if booking.status not in NEEDS_ATTENTION:
        raise AppError(409, "cannot_close", "This booking can't be closed.")
    audit.record(
        db,
        admin_id,
        "booking_closed_by_admin",
        "booking",
        str(booking.id),
        before={"status": booking.status.value},
        after={"status": "closed_by_admin", "reason": reason},
    )
    booking.status = BookingStatus.closed_by_admin
    booking.closed_by_admin_id = admin_id
    booking.close_reason = reason
    # Only if she did check in: checked_out_at needs checked_in_at (the "checked_out_needs_checked_in"
    # constraint), and if she never checked in there's no check-out time to stand in for.
    if booking.checked_in_at is not None and booking.checked_out_at is None:
        booking.checked_out_at = now
    db.commit()
    return booking
