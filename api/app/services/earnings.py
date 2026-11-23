"""What a sitter earns, and when it's released for payout (CLAUDE.md 6.2, 6.5, 6.8, 6.10; phase 9).

Earnings are recorded when a booking ends:
- at check-out: her level pay from check-in (or the start, if she was early) to the booked end, to the
  minute (6.2), plus her overtime pay if overtime was charged (6.8);
- on an admin's manual close: the same if she checked in; if she never did, whatever whole hours the admin
  chooses to pay her, none by default (Reuben, 2026-11-22);
- on a confirmed report (6.5): the show-up fee (₹100 per booked hour) when no one was home, a flat ₹100
  when only a man was home, her level pay for 1 hour for a child under 18 months, or, when she left
  because she felt unsafe, her level pay from check-in (or the start) until she reported, rounded up to
  the full hour (Reuben, 2026-11-22).

An earning is held until it can be released: the booking has ended, no overtime request is waiting for her
answer and no incident is open on it (6.9, 6.10). It's then due within 12 hours of being released (so 12
hours after check-out, the overtime answer, the admin's decision on a report, or the incident's
resolution, whichever is last; Reuben, 2026-11-22). An incident raised later holds it again until it's
resolved, unless it's already paid. Pay is the booking's plan level, which is her level when she took it.
Callers commit.
"""

import math
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Booking,
    BookingStatus,
    EarningKind,
    EarningStatus,
    Incident,
    IncidentStatus,
    OvertimeCharge,
    OvertimeRequest,
    OvertimeRequestStatus,
    SitterEarning,
)
from app.services import audit, sitter_pay

PAYOUT_WINDOW = timedelta(hours=12)  # 6.10, Sitter Terms 2.6
SHOW_UP_FEE_PER_HOUR_PAISE = 10_000  # ₹100 per booked hour when no one is home (6.5)
MAN_HOME_FEE_PAISE = 10_000  # a flat ₹100 when only a man is home (6.5)

# A booking that has ended, one way or another, with something she may be owed.
ENDED = (
    BookingStatus.completed,
    BookingStatus.closed_by_admin,
    BookingStatus.parent_absent,
    BookingStatus.declined_man_at_home,
    BookingStatus.child_under_age,
    BookingStatus.sitter_left_unsafe,
)


def _per_minute_paise(booking: Booking, minutes: int) -> int:
    """Her level pay for these minutes, to the nearest paisa."""
    return round(sitter_pay.PAY_PER_HOUR_PAISE[booking.plan] * minutes / 60)


def _add(db: Session, booking: Booking, kind: EarningKind, amount_paise: int, minutes: int | None) -> None:
    if amount_paise <= 0:
        return
    earning = SitterEarning(
        sitter_id=booking.sitter_id, booking_id=booking.id, kind=kind, amount_paise=amount_paise, minutes=minutes
    )
    db.add(earning)
    db.flush()
    audit.record(
        db,
        None,
        "earning_recorded",
        "sitter_earning",
        str(earning.id),
        after={"booking_id": str(booking.id), "kind": kind.value, "amount_paise": amount_paise, "minutes": minutes},
    )


def minutes_worked(booking: Booking) -> int:
    """Check-in (or the start, if she was early) to the booked end (6.2): a late check-in is paid from
    check-in; leaving before the end doesn't take anything off."""
    assert booking.checked_in_at is not None
    start = max(booking.checked_in_at, booking.starts_at)
    return max(0, int((booking.ends_at - start).total_seconds() // 60))


def _hours_worked_earning(db: Session, booking: Booking) -> None:
    minutes = minutes_worked(booking)
    _add(db, booking, EarningKind.booking, _per_minute_paise(booking, minutes), minutes)


def _overtime_earning(db: Session, booking: Booking) -> None:
    charge = db.scalar(select(OvertimeCharge).where(OvertimeCharge.booking_id == booking.id))
    if charge is not None:
        _add(db, booking, EarningKind.overtime, charge.sitter_pay_paise, charge.hours_charged * 60)


def record_check_out(db: Session, booking: Booking, now: datetime) -> None:
    """At check-out, after overtime is worked out."""
    _hours_worked_earning(db, booking)
    _overtime_earning(db, booking)
    release(db, booking, now)


def record_admin_close(db: Session, booking: Booking, pay_hours: int | None, now: datetime) -> None:
    """On an admin's manual close (6.7). If she never checked in, she's paid only the whole hours the admin
    chooses (none by default)."""
    if booking.checked_in_at is not None:
        _hours_worked_earning(db, booking)
    elif pay_hours:
        _add(db, booking, EarningKind.booking, sitter_pay.booking_pay_paise(booking.plan, pay_hours), pay_hours * 60)
    _overtime_earning(db, booking)
    release(db, booking, now)


def record_report(db: Session, booking: Booking, reported_at: datetime, now: datetime) -> None:
    """On a confirmed report: the booking's status says which (6.5). A no-show earns nothing."""
    if booking.status == BookingStatus.parent_absent:
        _add(db, booking, EarningKind.show_up_fee, SHOW_UP_FEE_PER_HOUR_PAISE * booking.units, None)
    elif booking.status == BookingStatus.declined_man_at_home:
        _add(db, booking, EarningKind.show_up_fee, MAN_HOME_FEE_PAISE, None)
    elif booking.status == BookingStatus.child_under_age:
        _add(db, booking, EarningKind.booking, sitter_pay.booking_pay_paise(booking.plan, 1), 60)
    elif booking.status == BookingStatus.sitter_left_unsafe:
        hours = unsafe_hours(booking, reported_at)
        _add(db, booking, EarningKind.booking, sitter_pay.booking_pay_paise(booking.plan, hours), hours * 60)
    release(db, booking, now)


def unsafe_hours(booking: Booking, reported_at: datetime) -> int:
    """Check-in (or the start) until she reported, rounded up to the full hour, at most the booked hours."""
    start = booking.checked_in_at or booking.starts_at
    seconds = max(0.0, (reported_at - start).total_seconds())
    return min(booking.units, max(1, math.ceil(seconds / 3600)))


def _waiting_on_overtime(db: Session, booking_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(OvertimeRequest.id).where(
                OvertimeRequest.booking_id == booking_id, OvertimeRequest.status == OvertimeRequestStatus.pending
            )
        )
        is not None
    )


def can_release(db: Session, booking: Booking) -> bool:
    return booking.status in ENDED and not _waiting_on_overtime(db, booking.id) and not open_incident(db, booking.id)


def open_incident(db: Session, booking_id: uuid.UUID) -> bool:
    # Same as incidents.has_open_incident; not imported, since incidents calls back into this module.
    return (
        db.scalar(
            select(Incident.id).where(Incident.booking_id == booking_id, Incident.status != IncidentStatus.resolved)
        )
        is not None
    )


def release(db: Session, booking: Booking, now: datetime) -> None:
    """Releases her held earnings for this booking if nothing holds them: due within 12 hours."""
    if not can_release(db, booking):
        return
    held = db.scalars(
        select(SitterEarning)
        .where(SitterEarning.booking_id == booking.id, SitterEarning.status == EarningStatus.held)
        .with_for_update()
    ).all()
    for earning in held:
        earning.status = EarningStatus.released
        earning.released_at = now
        earning.due_by = now + PAYOUT_WINDOW
        audit.record(
            db,
            None,
            "earning_released",
            "sitter_earning",
            str(earning.id),
            before={"status": "held"},
            after={"status": "released", "due_by": earning.due_by.isoformat()},
        )


def release_booking(db: Session, booking_id: uuid.UUID, now: datetime) -> None:
    booking = db.get(Booking, booking_id)
    if booking is not None:
        release(db, booking, now)


def hold(db: Session, booking_id: uuid.UUID) -> None:
    """An incident was raised: anything released but not yet paid is held again (6.9)."""
    released = db.scalars(
        select(SitterEarning)
        .where(SitterEarning.booking_id == booking_id, SitterEarning.status == EarningStatus.released)
        .with_for_update()
    ).all()
    for earning in released:
        earning.status = EarningStatus.held
        earning.released_at = None
        earning.due_by = None
        audit.record(
            db,
            None,
            "earning_held",
            "sitter_earning",
            str(earning.id),
            before={"status": "released"},
            after={"status": "held", "reason": "incident"},
        )


def for_booking(db: Session, booking_id: uuid.UUID) -> list[SitterEarning]:
    return list(
        db.scalars(select(SitterEarning).where(SitterEarning.booking_id == booking_id).order_by(SitterEarning.kind))
    )
