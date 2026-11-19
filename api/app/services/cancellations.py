"""Cancelling a booking (CLAUDE.md 6.5; phase 7 "Cancellations").

| Who    | When                         | Money                                  | Status                  |
| ------ | ---------------------------- | -------------------------------------- | ----------------------- |
| Parent | 3 hours or more before start | refunded in full                       | `cancelled_parent`      |
| Parent | less than 3 hours            | the whole booking is charged           | `cancelled_parent_late` |
| Sitter | 8 hours or more before start | the parent is refunded; no penalty     | `cancelled_sitter`      |
| Sitter | less than 8 hours            | refunded; she earns nothing; a strike  | `cancelled_sitter_late` |

Exactly 3 (or 8) hours before counts as in time. Only bookings that haven't started can be cancelled.

A parent can also withdraw a request the sitter hasn't answered, or an accepted booking not yet paid:
nothing has been paid, so nothing is refunded. A UPI reference that is still being checked when the
booking is cancelled is decided later: if an admin confirms it, it's refunded (or kept, for a late
parent cancellation); if they reject it after a late parent cancellation, the price is owed as a
cancellation charge (`payments`).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Booking, BookingStatus, Payment, Sitter, StrikeReason
from app.services import audit, bookings, strikes

PARENT_NOTICE = timedelta(hours=3)
SITTER_NOTICE = timedelta(hours=8)

# What each side can cancel. The parent: a request, an accepted booking waiting for payment, a paid one
# (and older paid ones still waiting for a child's verification). The sitter: what she has accepted.
PARENT_CAN_CANCEL = (
    BookingStatus.requested,
    BookingStatus.pending_payment,
    BookingStatus.awaiting_verification,
    BookingStatus.confirmed,
)
SITTER_CAN_CANCEL = (BookingStatus.pending_payment, BookingStatus.confirmed)


@dataclass(frozen=True)
class Cancelled:
    booking: Booking
    late: bool
    refunds: list[Payment]
    strike: strikes.Outcome | None = None  # a late sitter cancellation's strike, and her block
    # Who to tell: the sitter only if she had accepted it (a request she never saw needs no email).
    was_accepted: bool = False


def parent_late(booking: Booking, now: datetime) -> bool:
    return booking.starts_at - now < PARENT_NOTICE


def sitter_late(booking: Booking, now: datetime) -> bool:
    return booking.starts_at - now < SITTER_NOTICE


def _locked(db: Session, booking_id: uuid.UUID, **owner) -> Booking:
    query = select(Booking).where(Booking.id == booking_id)
    for column, value in owner.items():
        query = query.where(getattr(Booking, column) == value)
    booking = db.scalar(query.with_for_update())
    if booking is None:
        raise AppError(404, "not_found", "We couldn't find that booking.")
    return booking


def _record(db: Session, actor_id: uuid.UUID, booking: Booking, status: BookingStatus, now: datetime) -> None:
    audit.record(
        db,
        actor_id,
        "booking_cancelled",
        "booking",
        str(booking.id),
        before={"status": booking.status.value},
        after={
            "status": status.value,
            "hours_before_start": round((booking.starts_at - now).total_seconds() / 3600, 2),
        },
    )
    booking.status = status


def by_parent(db: Session, parent_id: uuid.UUID, booking_id: uuid.UUID, now: datetime) -> Cancelled:
    booking = _locked(db, booking_id, parent_id=parent_id)
    if booking.status not in PARENT_CAN_CANCEL:
        raise AppError(409, "cannot_cancel", "This booking can't be cancelled.")
    if booking.starts_at <= now:
        raise AppError(409, "already_started", "This booking has already started, so it can't be cancelled here.")
    was_accepted = booking.status != BookingStatus.requested
    late = parent_late(booking, now)
    _record(
        db, parent_id, booking, BookingStatus.cancelled_parent_late if late else BookingStatus.cancelled_parent, now
    )
    db.flush()
    # In time: every confirmed payment comes back. Late: the whole booking is charged, so nothing does.
    refunds = [] if late else bookings.refund_booking(db, parent_id, booking.id)
    db.commit()
    return Cancelled(booking, late, refunds, was_accepted=was_accepted)


def by_sitter(db: Session, sitter_id: uuid.UUID, booking_id: uuid.UUID, now: datetime) -> Cancelled:
    # Her row first, as when she accepts, so her answers take turns.
    db.execute(select(Sitter.profile_id).where(Sitter.profile_id == sitter_id).with_for_update())
    booking = _locked(db, booking_id, sitter_id=sitter_id)
    if booking.status not in SITTER_CAN_CANCEL:
        raise AppError(409, "cannot_cancel", "This booking can't be cancelled.")
    if booking.starts_at <= now:
        raise AppError(409, "already_started", "This booking has already started, so it can't be cancelled here.")
    late = sitter_late(booking, now)
    _record(
        db, sitter_id, booking, BookingStatus.cancelled_sitter_late if late else BookingStatus.cancelled_sitter, now
    )
    db.flush()
    # The parent's money always comes back when the sitter cancels.
    refunds = bookings.refund_booking(db, sitter_id, booking.id)
    outcome = None
    if late:  # given by the rules, not a person
        outcome = strikes.give(db, None, sitter_id, StrikeReason.late_cancellation, now, booking_id=booking.id)
    db.commit()
    return Cancelled(booking, late, refunds, outcome, was_accepted=True)
