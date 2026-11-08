"""A sitter's free times (CLAUDE.md 6.4: a booking must fit inside the sitter's availability). Dated
time slots, added and removed by the sitter (design.md: no weekday toggles in v1)."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import AvailabilitySlot, Sitter

# The shortest booking is one hour (bookings are whole hours, CLAUDE.md 6.1), so a shorter free time
# could never be booked.
MIN_LENGTH = timedelta(hours=1)


def upcoming(db: Session, sitter_id: uuid.UUID, now: datetime) -> list[AvailabilitySlot]:
    return list(
        db.scalars(
            select(AvailabilitySlot)
            .where(AvailabilitySlot.sitter_id == sitter_id, AvailabilitySlot.ends_at > now)
            .order_by(AvailabilitySlot.starts_at)
        )
    )


def add(db: Session, sitter_id: uuid.UUID, starts_at: datetime, ends_at: datetime, now: datetime) -> AvailabilitySlot:
    if starts_at < now:
        raise AppError(422, "slot_in_the_past", "Choose a time that hasn't started yet")
    if ends_at - starts_at < MIN_LENGTH:
        raise AppError(422, "slot_too_short", "A free time needs to be at least an hour long")
    # Lock her row so two requests at once can't both add overlapping times.
    db.scalar(select(Sitter).where(Sitter.profile_id == sitter_id).with_for_update())
    overlapping = db.scalar(
        select(AvailabilitySlot.id).where(
            AvailabilitySlot.sitter_id == sitter_id,
            AvailabilitySlot.starts_at < ends_at,
            AvailabilitySlot.ends_at > starts_at,
        )
    )
    if overlapping is not None:
        raise AppError(409, "slot_overlaps", "This overlaps a time you've already added")
    slot = AvailabilitySlot(sitter_id=sitter_id, starts_at=starts_at, ends_at=ends_at)
    db.add(slot)
    db.commit()
    return slot


def remove(db: Session, sitter_id: uuid.UUID, slot_id: uuid.UUID) -> None:
    """Bookings (phase 7) will stop a booked time from being removed."""
    slot = db.get(AvailabilitySlot, slot_id)
    if slot is None:
        raise AppError(404, "not_found", "That time isn't on your list")
    if slot.sitter_id != sitter_id:  # no IDOR: can't touch another sitter's times
        raise AppError(403, "forbidden", "That time isn't on your list")
    db.delete(slot)
    db.commit()
