"""Check-in and check-out codes (CLAUDE.md 6.7; phase 8).

Each booking gets a 4-digit check-in code, and, once she's checked in, a 4-digit check-out code. A code
is generated the first time the parent asks to see it and kept encrypted at rest (never in plain text);
asking again just decrypts and returns the same one, so nothing is weakened by viewing it more than once.
The parent reads it out to the sitter, who enters it in her app, along with her location (if she allows
it; if not, that's recorded by leaving the location columns empty and check-in still goes ahead). Five
wrong codes locks the booking's codes and alerts admins; only an admin closing the booking manually
(the next phase 8 item) can move it on from there.

Check-in moves the booking to `in_progress`; check-out moves it to `completed`. Overtime and sitter pay
from hours worked are worked out elsewhere, once those phase 8/9 items exist.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Booking, BookingStatus
from app.services import audit, encryption
from app.services.availability import INDIA, today_in_india

MAX_ATTEMPTS = 5  # 6.7: lock after 5 wrong attempts


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
    db.commit()
    return Checked(booking)
