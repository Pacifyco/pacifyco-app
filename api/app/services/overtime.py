"""Overtime (CLAUDE.md 6.8; phase 8). During the booking the parent can ask for extra whole hours; the
sitter accepts or declines once they've agreed it between them -- nothing is charged either way.

Overtime itself is always worked out at check-out, whether or not a request was ever made or accepted:
a parent who's simply running late still owes it. Checked-out time past the booked end is rounded up to
the next full hour and charged at the plan's price, or the next tier's price for the hours that fall past
the plan's own latest end (6.8) -- the sitter is still paid her own level's pay for every hour she works."""

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import (
    Booking,
    BookingStatus,
    OvertimeCharge,
    OvertimeRequest,
    OvertimeRequestStatus,
    Payment,
    PaymentKind,
    PaymentStatus,
)
from app.models import SitterLevel as Plan
from app.services import audit, earnings, pricing, sitter_pay
from app.services.availability import INDIA
from app.services.bookings import LATEST_END

OVERTIME_PAYMENT_WINDOW = timedelta(hours=2)  # 6.8: payable within 2 hours

# Pause overage is charged at Unwind's rate, Unwind overage at Recharge's; Recharge has no higher tier,
# so for now overage past midnight on Recharge is charged at the Recharge rate itself (deferred default,
# decided 2026-11-03 -- revisit if it comes up in practice).
NEXT_TIER: dict[Plan, Plan] = {
    Plan.pause: Plan.unwind,
    Plan.unwind: Plan.recharge,
    Plan.recharge: Plan.recharge,
}


def _booking(db: Session, booking_id: uuid.UUID, **owner: uuid.UUID) -> Booking:
    query = select(Booking).where(Booking.id == booking_id)
    for column, value in owner.items():
        query = query.where(getattr(Booking, column) == value)
    booking = db.scalar(query.with_for_update())
    if booking is None:
        raise AppError(404, "not_found", "We couldn't find that booking.")
    return booking


def for_booking(db: Session, booking_id: uuid.UUID) -> OvertimeRequest | None:
    """The booking's latest overtime request, if any."""
    return db.scalar(
        select(OvertimeRequest)
        .where(OvertimeRequest.booking_id == booking_id)
        .order_by(OvertimeRequest.requested_at.desc())
    )


def request(db: Session, parent_id: uuid.UUID, booking_id: uuid.UUID, hours: int, now: datetime) -> OvertimeRequest:
    """The parent asks for extra whole hours, only while the booking is under way (6.8)."""
    booking = _booking(db, booking_id, parent_id=parent_id)
    if booking.status != BookingStatus.in_progress:
        raise AppError(409, "not_now", "You can request overtime once the booking has started.")
    open_request = db.scalar(
        select(OvertimeRequest.id).where(
            OvertimeRequest.booking_id == booking.id, OvertimeRequest.status == OvertimeRequestStatus.pending
        )
    )
    if open_request is not None:
        raise AppError(409, "already_requested", "There's already a request waiting for her answer.")
    overtime_request = OvertimeRequest(booking_id=booking.id, requested_hours=hours, requested_at=now)
    db.add(overtime_request)
    db.flush()
    audit.record(
        db,
        parent_id,
        "overtime_requested",
        "overtime_request",
        str(overtime_request.id),
        after={"booking_id": str(booking.id), "hours": hours},
    )
    db.commit()
    return overtime_request


def _open_request_for_sitter(db: Session, sitter_id: uuid.UUID, request_id: uuid.UUID) -> OvertimeRequest:
    overtime_request = db.scalar(select(OvertimeRequest).where(OvertimeRequest.id == request_id).with_for_update())
    if overtime_request is None:
        raise AppError(404, "not_found", "We couldn't find that request.")
    hers = db.scalar(
        select(Booking.id).where(Booking.id == overtime_request.booking_id, Booking.sitter_id == sitter_id)
    )
    if hers is None:
        raise AppError(404, "not_found", "We couldn't find that request.")
    if overtime_request.status != OvertimeRequestStatus.pending:
        raise AppError(409, "already_decided", "This request has already been answered.")
    return overtime_request


def decide(db: Session, sitter_id: uuid.UUID, request_id: uuid.UUID, accept: bool, now: datetime) -> OvertimeRequest:
    """She accepts or declines (6.8): nothing is charged either way, it's just between them."""
    overtime_request = _open_request_for_sitter(db, sitter_id, request_id)
    overtime_request.status = OvertimeRequestStatus.accepted if accept else OvertimeRequestStatus.declined
    overtime_request.decided_at = now
    audit.record(
        db,
        sitter_id,
        "overtime_decided",
        "overtime_request",
        str(overtime_request.id),
        after={"status": overtime_request.status.value},
    )
    # Her pay waits for her answer if the booking has already ended (6.10).
    earnings.release_booking(db, overtime_request.booking_id, now)
    db.commit()
    return overtime_request


@dataclass(frozen=True)
class Charged:
    charge: OvertimeCharge
    payment: Payment


def charge_for_checkout(db: Session, booking: Booking, now: datetime) -> Charged | None:
    """Worked out at check-out (6.8), whether or not a request was ever made or accepted: if she checked
    out past the booked end, the extra time is rounded up to the full hour and charged, at the plan's
    price, or the next tier's for the hours that fall past the plan's own latest end. She's paid her own
    level pay for the same hours either way. Charges once per booking -- the caller commits."""
    assert booking.checked_out_at is not None
    seconds_over = (booking.checked_out_at - booking.ends_at).total_seconds()
    if seconds_over <= 0:
        return None
    return _charge(db, None, booking, math.ceil(seconds_over / 3600), int(seconds_over // 60), now, "check_out")


# An admin's manual close (6.7) charges no overtime by itself; the admin may choose to (Reuben, 2026-11-21).
MAX_CLOSE_HOURS = 6


def charge_on_close(db: Session, admin_id: uuid.UUID, booking: Booking, hours: int, now: datetime) -> Charged:
    """The admin closing a booking by hand chooses to charge whole hours of overtime past the booked end,
    priced as at check-out. The parent is told and pays within 2 hours. The caller commits."""
    if not 1 <= hours <= MAX_CLOSE_HOURS:
        raise AppError(422, "invalid_overtime_hours", f"Overtime is 1 to {MAX_CLOSE_HOURS} whole hours.")
    if db.scalar(select(OvertimeCharge.id).where(OvertimeCharge.booking_id == booking.id)) is not None:
        raise AppError(409, "overtime_already_charged", "Overtime has already been charged for this booking.")
    return _charge(db, admin_id, booking, hours, hours * 60, now, "admin_close")


def _charge(
    db: Session,
    actor_id: uuid.UUID | None,
    booking: Booking,
    hours_over: int,
    minutes_over: int,
    now: datetime,
    source: str,
) -> Charged:
    """The charge for these whole hours past the booked end: the plan's price, or the next tier's for the
    hours past the plan's own latest end (6.8); she's paid her level pay for the same hours."""
    midnight = datetime.combine(booking.starts_at.astimezone(INDIA).date(), time(), INDIA)
    latest_end = midnight + LATEST_END[booking.plan]
    amount_paise = 0
    for hour in range(hours_over):
        hour_end = booking.ends_at + timedelta(hours=hour + 1)
        plan = booking.plan if hour_end <= latest_end else NEXT_TIER[booking.plan]
        amount_paise += pricing.hourly_price_paise(plan, booking.children_count)
    sitter_pay_paise = sitter_pay.booking_pay_paise(booking.plan, hours_over)

    charge = OvertimeCharge(
        booking_id=booking.id,
        minutes_over=minutes_over,
        hours_charged=hours_over,
        amount_paise=amount_paise,
        sitter_pay_paise=sitter_pay_paise,
    )
    db.add(charge)
    payment = Payment(
        booking_id=booking.id,
        parent_id=booking.parent_id,
        kind=PaymentKind.overtime,
        amount_paise=amount_paise,
        status=PaymentStatus.pending,
        due_by=now + OVERTIME_PAYMENT_WINDOW,
    )
    db.add(payment)
    db.flush()
    audit.record(
        db,
        actor_id,
        "overtime_charged",
        "booking",
        str(booking.id),
        after={
            "hours_charged": hours_over,
            "amount_paise": amount_paise,
            "payment_id": str(payment.id),
            "source": source,
        },
    )
    return Charged(charge, payment)
