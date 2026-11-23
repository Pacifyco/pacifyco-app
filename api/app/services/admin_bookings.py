"""The admin bookings overview and manual adjustments (phase 10; Reuben, 2026-11-23).

Each adjustment needs a reason, is audit logged, and the people affected are emailed:

- **Cancel** a booking that hasn't started (`cancelled_by_admin`): refunded in full, no strike, both told.
  Also used when an admin suspends or removes an account (`account_status`).
- **Refund part** of what was paid for a booking (a goodwill or correction refund): a new refund row, up to
  what's been paid and not yet refunded. Money rows are never edited.
- **Add pay** for the sitter (a bonus or a correction) once the booking has ended or been cancelled: an
  `adjustment` earning with a note she sees, due within 12 hours like any other (held while an incident on
  the booking is open).
- **Waive** an unpaid overtime or cancellation charge: `waived`, so it's no longer owed and stops blocking
  new bookings. Not while a payment the parent sent for it is waiting to be checked.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.errors import AppError
from app.models import (
    Booking,
    BookingStatus,
    EarningKind,
    EarningStatus,
    Payment,
    PaymentKind,
    PaymentStatus,
    Profile,
    SitterEarning,
)
from app.services import audit, bookings, earnings
from app.services.availability import INDIA

PAGE_SIZE = 50
REASON_MAX = 1000
MAX_EXTRA_PAY_PAISE = 1_000_000  # ₹10,000 at a time: a guard against typing too many zeros

# Not started: what can still be cancelled.
UPCOMING = (
    BookingStatus.requested,
    BookingStatus.pending_payment,
    BookingStatus.awaiting_verification,
    BookingStatus.confirmed,
)
# Finished, one way or another, with care given or a report decided.
PAST = (
    BookingStatus.completed,
    BookingStatus.closed_by_admin,
    BookingStatus.parent_absent,
    BookingStatus.declined_man_at_home,
    BookingStatus.child_under_age,
    BookingStatus.sitter_left_unsafe,
    BookingStatus.sitter_no_show,
)
GROUPS = ("upcoming", "under_way", "past", "cancelled")
CHARGE_KINDS = (PaymentKind.overtime, PaymentKind.cancellation_charge)


def _reason(reason: str) -> str:
    cleaned = reason.strip()
    if not cleaned:
        raise AppError(422, "reason_required", "Please give a reason.")
    if len(cleaned) > REASON_MAX:
        raise AppError(422, "reason_too_long", f"Please keep the reason under {REASON_MAX} characters.")
    return cleaned


def _group_filter(query: Select, group: str, now: datetime) -> Select:
    if group == "upcoming":
        return query.where(Booking.status.in_(UPCOMING), Booking.starts_at > now)
    if group == "under_way":
        return query.where(
            or_(
                Booking.status == BookingStatus.in_progress,
                (Booking.status == BookingStatus.confirmed) & (Booking.starts_at <= now),
            )
        )
    if group == "past":
        return query.where(Booking.status.in_(PAST))
    # Cancelled, declined or lapsed; and anything not started whose start has passed unpaid or unanswered.
    return query.where(
        Booking.status.not_in((*UPCOMING, *PAST, BookingStatus.in_progress))
        | (Booking.status.in_(UPCOMING) & (Booking.status != BookingStatus.confirmed) & (Booking.starts_at <= now))
    )


@dataclass(frozen=True)
class Listed:
    booking: Booking
    parent_name: str | None
    sitter_name: str | None


def overview(
    db: Session,
    now: datetime,
    *,
    group: str | None = None,
    q: str | None = None,
    starts_from: date | None = None,
    starts_to: date | None = None,
    page: int = 0,
) -> tuple[list[Listed], bool]:
    """Bookings, latest start first, a page at a time; and whether there are more."""
    parent = aliased(Profile)
    sitter = aliased(Profile)
    query = (
        select(Booking, parent.full_name, sitter.full_name)
        .join(parent, parent.id == Booking.parent_id)
        .join(sitter, sitter.id == Booking.sitter_id)
    )
    if group in GROUPS:
        query = _group_filter(query, group, now)
    text = (q or "").strip()[:100]
    if text:
        escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped}%"
        query = query.where(or_(parent.full_name.ilike(like, escape="\\"), sitter.full_name.ilike(like, escape="\\")))
    if starts_from is not None:  # India dates
        query = query.where(Booking.starts_at >= datetime.combine(starts_from, time(), INDIA))
    if starts_to is not None:
        query = query.where(Booking.starts_at < datetime.combine(starts_to + timedelta(days=1), time(), INDIA))
    found = db.execute(
        query.order_by(Booking.starts_at.desc(), Booking.id).offset(max(page, 0) * PAGE_SIZE).limit(PAGE_SIZE + 1)
    ).all()
    return [Listed(booking, p, s) for booking, p, s in found[:PAGE_SIZE]], len(found) > PAGE_SIZE


def _booking(db: Session, booking_id: uuid.UUID) -> Booking:
    booking = db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
    if booking is None:
        raise AppError(404, "not_found", "We couldn't find that booking.")
    return booking


# ---------- cancelling ----------


def cancel_by_admin(db: Session, admin_id: uuid.UUID, booking: Booking, why: dict) -> list[Payment]:
    """Cancelled by Pacifyco before the start: refunded in full, no strike. The caller commits."""
    audit.record(
        db,
        admin_id,
        "booking_cancelled",
        "booking",
        str(booking.id),
        before={"status": booking.status.value},
        after={"status": BookingStatus.cancelled_by_admin.value, **why},
    )
    booking.status = BookingStatus.cancelled_by_admin
    db.flush()
    return bookings.refund_booking(db, admin_id, booking.id)


@dataclass(frozen=True)
class Cancelled:
    booking: Booking
    reason: str
    refunds: list[Payment]
    was_accepted: bool  # the sitter had accepted it, or could see the request


def cancel(db: Session, admin_id: uuid.UUID, booking_id: uuid.UUID, reason: str, now: datetime) -> Cancelled:
    reason = _reason(reason)
    booking = _booking(db, booking_id)
    if booking.status not in UPCOMING or booking.starts_at <= now:
        raise AppError(409, "cannot_cancel", "Only a booking that hasn't started can be cancelled.")
    was_accepted = booking.status != BookingStatus.requested or booking.request_visible_at is not None
    refunds = cancel_by_admin(db, admin_id, booking, {"reason": reason})
    db.commit()
    return Cancelled(booking, reason, refunds, was_accepted)


# ---------- refunding part of a booking ----------


def refundable_paise(db: Session, booking_id: uuid.UUID) -> int:
    """Paid for this booking (its payments and charges, confirmed) less what's already refunded or owed back."""
    paid = db.scalar(
        select(func.coalesce(func.sum(Payment.amount_paise), 0)).where(
            Payment.booking_id == booking_id,
            Payment.kind != PaymentKind.refund,
            Payment.status == PaymentStatus.confirmed,
        )
    )
    refunded = db.scalar(
        select(func.coalesce(func.sum(Payment.amount_paise), 0)).where(
            Payment.booking_id == booking_id,
            Payment.kind == PaymentKind.refund,
            Payment.status.in_((PaymentStatus.pending, PaymentStatus.confirmed)),
        )
    )
    return max(0, int(paid or 0) + int(refunded or 0))


def refund(
    db: Session, admin_id: uuid.UUID, booking_id: uuid.UUID, amount_paise: int, reason: str
) -> tuple[Booking, Payment]:
    reason = _reason(reason)
    booking = _booking(db, booking_id)
    available = refundable_paise(db, booking.id)
    if available == 0:
        raise AppError(409, "nothing_to_refund", "Nothing paid for this booking is left to refund.")
    if amount_paise <= 0 or amount_paise > available:
        raise AppError(
            422, "refund_too_much", "The refund must be more than ₹0 and no more than what's left to refund."
        )
    row = Payment(
        booking_id=booking.id,
        parent_id=booking.parent_id,
        kind=PaymentKind.refund,
        amount_paise=-amount_paise,
        status=PaymentStatus.pending,
    )
    db.add(row)
    db.flush()
    audit.record(
        db,
        admin_id,
        "refund_owed",
        "payment",
        str(row.id),
        after={"booking_id": str(booking.id), "amount_paise": row.amount_paise, "reason": reason, "partial": True},
    )
    db.commit()
    return booking, row


# ---------- extra pay for the sitter ----------


def add_pay(
    db: Session, admin_id: uuid.UUID, booking_id: uuid.UUID, amount_paise: int, note: str, now: datetime
) -> SitterEarning:
    note = _reason(note)
    booking = _booking(db, booking_id)
    if booking.status in (*UPCOMING, BookingStatus.in_progress):
        raise AppError(409, "booking_not_over", "Extra pay can be added once the booking has ended or been cancelled.")
    if amount_paise <= 0 or amount_paise > MAX_EXTRA_PAY_PAISE:
        raise AppError(422, "extra_pay_amount", "Extra pay must be more than ₹0 and at most ₹10,000 at a time.")
    earning = SitterEarning(
        sitter_id=booking.sitter_id,
        booking_id=booking.id,
        kind=EarningKind.adjustment,
        amount_paise=amount_paise,
        note=note,
    )
    db.add(earning)
    db.flush()
    audit.record(
        db,
        admin_id,
        "earning_recorded",
        "sitter_earning",
        str(earning.id),
        after={"booking_id": str(booking.id), "kind": earning.kind.value, "amount_paise": amount_paise, "note": note},
    )
    if booking.status in earnings.ENDED:
        earnings.release(db, booking, now)  # the usual rules: no overtime answer waiting, no open incident
    elif not earnings.open_incident(db, booking.id):
        earning.status = EarningStatus.released
        earning.released_at = now
        earning.due_by = now + earnings.PAYOUT_WINDOW
        audit.record(
            db,
            admin_id,
            "earning_released",
            "sitter_earning",
            str(earning.id),
            before={"status": "held"},
            after={"status": "released", "due_by": earning.due_by.isoformat()},
        )
    db.commit()
    return earning


# ---------- waiving a charge ----------


def waive(db: Session, admin_id: uuid.UUID, payment_id: uuid.UUID, reason: str, now: datetime) -> Payment:
    reason = _reason(reason)
    charge = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if charge is None or charge.kind not in CHARGE_KINDS:
        raise AppError(404, "not_found", "We couldn't find that charge.")
    if charge.status != PaymentStatus.pending:
        raise AppError(409, "not_owed", "This charge is no longer owed.")
    if charge.upi_reference is not None:
        raise AppError(
            409, "payment_being_checked", "The parent has sent a payment for this charge. Confirm or reject it first."
        )
    audit.record(
        db,
        admin_id,
        "charge_waived",
        "payment",
        str(charge.id),
        before={"status": charge.status.value},
        after={"status": PaymentStatus.waived.value, "amount_paise": charge.amount_paise, "reason": reason},
    )
    charge.status = PaymentStatus.waived
    charge.waive_reason = reason
    charge.confirmed_by = admin_id
    charge.confirmed_at = now
    db.commit()
    return charge
