"""Paying for a booking (CLAUDE.md 6.1; phase 6 "Booking payment").

Beta, manual UPI: the parent pays the full price to Pacifyco's UPI ID (`PACIFY_UPI_ID`), from a
`upi://pay` link or its QR code, then enters the 12-digit UPI reference. That adds a `pending` payment
row; an admin checks it and confirms or rejects it (next item). Payment rows are append-only (5).

Razorpay replaces this later (3): `payment_instructions` and `submit_upi_reference` are the parts it
swaps out.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import quote, urlencode

from sqlalchemy import String, and_, cast, exists, or_, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import AuditLog, Booking, BookingStatus, Payment, PaymentKind, PaymentStatus, Profile
from app.services import audit
from app.services import bookings as bookings_service

PAYEE_NAME = "Pacifyco"
UPI_REFERENCE = re.compile(r"^[0-9]{12}$")


@dataclass(frozen=True)
class PaymentInstructions:
    upi_id: str
    payee_name: str
    amount_paise: int
    note: str
    upi_link: str


def booking_note(booking_id: uuid.UUID) -> str:
    """Shown in the UPI app and on Pacifyco's statement, so an admin can match the payment."""
    return f"Pacifyco booking {str(booking_id)[:8].upper()}"


def charge_note(payment_id: uuid.UUID) -> str:
    """The note for paying a charge (a late cancellation now, overtime later), to match it the same way."""
    return f"Pacifyco charge {str(payment_id)[:8].upper()}"


def _instructions(upi_id: str, amount_paise: int, note: str) -> PaymentInstructions | None:
    """How to pay this amount by UPI, or None while Pacifyco's UPI ID isn't set."""
    if not upi_id:
        return None
    params = {
        "pa": upi_id,
        "pn": PAYEE_NAME,
        "am": f"{amount_paise // 100}.{amount_paise % 100:02d}",
        "cu": "INR",
        "tn": note,
    }
    link = "upi://pay?" + urlencode(params, quote_via=quote, safe="@")
    return PaymentInstructions(upi_id, PAYEE_NAME, amount_paise, note, link)


def payment_instructions(upi_id: str, booking: Booking) -> PaymentInstructions | None:
    """How to pay for this booking, or None while Pacifyco's UPI ID isn't set."""
    return _instructions(upi_id, booking.price_paise, booking_note(booking.id))


def charge_instructions(upi_id: str, charge: Payment) -> PaymentInstructions | None:
    return _instructions(upi_id, charge.amount_paise, charge_note(charge.id))


def latest_booking_payment(db: Session, booking_id: uuid.UUID) -> Payment | None:
    return db.scalar(
        select(Payment)
        .where(Payment.booking_id == booking_id, Payment.kind == PaymentKind.booking)
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .limit(1)
    )


def submit_upi_reference(db: Session, parent: Profile, booking_id: uuid.UUID, reference: str, now: datetime) -> Payment:
    """The parent says they've paid: one `pending` booking payment for the full price, for an admin to
    check. A rejected payment can be followed by a new reference."""
    booking = bookings_service.parents_booking(db, parent.id, booking_id)
    reference = reference.strip()
    if not UPI_REFERENCE.match(reference):
        raise AppError(422, "invalid_upi_reference", "Please enter the 12-digit UPI reference from your UPI app.")
    # Lock and re-read the booking, so two submissions at once, or the auto-cancel job, can't race this.
    db.refresh(booking, with_for_update=True)
    if booking.status != BookingStatus.pending_payment:
        raise AppError(409, "not_waiting_for_payment", "This booking isn't waiting for a payment.")
    if now >= bookings_service.pay_by(booking):
        raise AppError(
            409, "payment_deadline_passed", "The time to pay for this booking has passed, so it can't be paid now."
        )
    latest = latest_booking_payment(db, booking.id)
    if latest is not None and latest.status != PaymentStatus.rejected:
        raise AppError(409, "payment_already_sent", "You've already sent the payment for this booking.")
    used = db.scalar(
        select(Payment.id).where(Payment.upi_reference == reference, Payment.status != PaymentStatus.rejected)
    )
    if used is not None:
        raise AppError(
            409, "upi_reference_used", "That UPI reference has already been sent. Please check it and try again."
        )

    payment = Payment(
        booking_id=booking.id,
        parent_id=parent.id,
        kind=PaymentKind.booking,
        amount_paise=booking.price_paise,
        status=PaymentStatus.pending,
        upi_reference=reference,
        due_by=bookings_service.pay_by(booking),
    )
    db.add(payment)
    db.flush()
    audit.record(
        db,
        parent.id,
        "payment_submitted",
        "payment",
        str(payment.id),
        after={
            "booking_id": str(booking.id),
            "kind": payment.kind.value,
            "amount_paise": payment.amount_paise,
            "status": payment.status.value,
        },
    )
    db.commit()
    return payment


# ---------- paying a charge (6.5, 6.8) ----------
#
# A charge (a late cancellation's price now; overtime in phase 8) is a `pending` row: money owed. The parent
# pays it by UPI and sends the 12-digit reference, kept on the charge itself; an admin confirms it (paid)
# or rejects the reference (it's cleared, with the reason shown, and the charge is still owed). Until an
# admin confirms it, it's still owed, so it keeps blocking new bookings (6.4).

CHARGE_KINDS = (PaymentKind.cancellation_charge, PaymentKind.overtime)


def parents_charge(db: Session, parent_id: uuid.UUID, payment_id: uuid.UUID) -> Payment:
    charge = db.scalar(
        select(Payment).where(Payment.id == payment_id, Payment.parent_id == parent_id, Payment.kind.in_(CHARGE_KINDS))
    )
    if charge is None:
        raise AppError(404, "not_found", "We couldn't find that charge.")
    return charge


def submit_charge_reference(
    db: Session, parent: Profile, payment_id: uuid.UUID, reference: str, now: datetime
) -> Payment:
    """The parent says they've paid a charge: the reference is kept on it for an admin to check."""
    charge = parents_charge(db, parent.id, payment_id)
    reference = reference.strip()
    if not UPI_REFERENCE.match(reference):
        raise AppError(422, "invalid_upi_reference", "Please enter the 12-digit UPI reference from your UPI app.")
    db.refresh(charge, with_for_update=True)
    if charge.status != PaymentStatus.pending:
        raise AppError(409, "not_waiting_for_payment", "This charge isn't waiting for a payment.")
    if charge.upi_reference is not None:
        raise AppError(409, "payment_already_sent", "You've already sent the payment for this charge.")
    used = db.scalar(
        select(Payment.id).where(Payment.upi_reference == reference, Payment.status != PaymentStatus.rejected)
    )
    if used is not None:
        raise AppError(
            409, "upi_reference_used", "That UPI reference has already been sent. Please check it and try again."
        )
    charge.upi_reference = reference
    charge.rejection_reason = None  # an earlier reference's rejection no longer applies
    audit.record(
        db,
        parent.id,
        CHARGE_SENT,
        "payment",
        str(charge.id),
        after={"kind": charge.kind.value, "amount_paise": charge.amount_paise},
    )
    db.commit()
    return charge


CHARGE_SENT = "charge_payment_submitted"


def reference_sent_at(db: Session, charge: Payment) -> datetime | None:
    """When the parent sent the charge's current reference (from the audit log)."""
    return db.scalar(
        select(AuditLog.created_at)
        .where(AuditLog.action == CHARGE_SENT, AuditLog.entity == "payment", AuditLog.entity_id == str(charge.id))
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )


def sent_charge(db: Session, payment_id: uuid.UUID) -> Payment | None:
    """A charge with a reference waiting for an admin, locked; None if it isn't a charge."""
    charge = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if charge is None or charge.kind not in CHARGE_KINDS:
        return None
    if charge.status != PaymentStatus.pending or charge.upi_reference is None:
        raise AppError(409, "payment_already_decided", "This payment has already been confirmed or rejected.")
    return charge


def confirm_charge(db: Session, admin_id: uuid.UUID, charge: Payment, now: datetime) -> Payment:
    """The money for the charge is in Pacifyco's account: it's paid and no longer owed."""
    charge.status = PaymentStatus.confirmed
    charge.confirmed_by = admin_id
    charge.confirmed_at = now
    audit.record(
        db,
        admin_id,
        "payment_confirmed",
        "payment",
        str(charge.id),
        before={"status": PaymentStatus.pending.value},
        after={"status": charge.status.value, "kind": charge.kind.value, "amount_paise": charge.amount_paise},
    )
    db.commit()
    return charge


def reject_charge_reference(db: Session, admin_id: uuid.UUID, charge: Payment, reason: str) -> Payment:
    """The money didn't arrive: the reference is cleared, the parent sees why, and the charge is still owed."""
    audit.record(
        db,
        admin_id,
        "charge_reference_rejected",
        "payment",
        str(charge.id),
        before={"upi_reference": charge.upi_reference},
        after={"upi_reference": None, "reason": reason},
    )
    charge.upi_reference = None
    charge.rejection_reason = reason
    db.commit()
    return charge


# ---------- an admin's decision (6.1) ----------


@dataclass(frozen=True)
class Confirmed:
    payment: Payment
    booking: Booking
    # The payment was received but the booking can't go ahead (another booking took her time first):
    # the refund now owed.
    refund: Payment | None
    # Other unpaid bookings for an overlapping time with her, cancelled because this one was paid first.
    cancelled: list[uuid.UUID]


def _pending_booking_payment(db: Session, payment_id: uuid.UUID) -> tuple[Payment, Booking]:
    payment = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if payment is None or payment.kind != PaymentKind.booking:
        raise AppError(404, "not_found", "We couldn't find that payment.")
    if payment.status != PaymentStatus.pending:
        raise AppError(409, "payment_already_decided", "This payment has already been confirmed or rejected.")
    booking = db.scalar(select(Booking).where(Booking.id == payment.booking_id).with_for_update())
    assert booking is not None  # RESTRICT foreign key
    return payment, booking


def confirm(db: Session, admin_id: uuid.UUID, payment_id: uuid.UUID, now: datetime) -> Confirmed:
    """The money is in Pacifyco's account. If the booking can still go ahead it's `confirmed` and wins
    her time, or, with a child not yet verified, `awaiting_verification` (her time stays free until then,
    Reuben 2026-11-18); if another booking took the time first, it's cancelled and a refund is owed.
    A booking whose start has passed can't be confirmed (an open question in progress.md)."""
    payment, booking = _pending_booking_payment(db, payment_id)
    if booking.status == BookingStatus.pending_payment and booking.starts_at <= now:
        raise AppError(
            409,
            "booking_started",
            "This booking's start time has passed, so it can't be confirmed. Please contact the parent.",
        )
    payment.status = PaymentStatus.confirmed
    payment.confirmed_by = admin_id
    payment.confirmed_at = now
    audit.record(
        db,
        admin_id,
        "payment_confirmed",
        "payment",
        str(payment.id),
        before={"status": PaymentStatus.pending.value},
        after={"status": payment.status.value, "booking_id": str(booking.id), "amount_paise": payment.amount_paise},
    )

    cancelled: list[uuid.UUID] = []
    refund = None
    if booking.status == BookingStatus.pending_payment and bookings_service.slot_taken(
        db, booking, bookings_service.CONFIRMED
    ):
        _cancel_taken(db, booking)
    if booking.status == BookingStatus.pending_payment:
        cancelled = bookings_service.mark_paid(db, admin_id, booking)
    elif booking.status != BookingStatus.cancelled_parent_late:
        refund = _owe_refund(db, admin_id, payment)
    # A late parent cancellation is charged in full (6.5): that money is kept.
    db.commit()
    return Confirmed(payment, booking, refund, cancelled)


def _cancel_taken(db: Session, booking: Booking) -> None:
    taken_by = bookings_service._holder(db, booking)
    audit.record(
        db,
        None,
        "booking_cancelled",
        "booking",
        str(booking.id),
        before={"status": booking.status.value},
        after={"status": BookingStatus.cancelled_slot_taken.value, "taken_by": str(taken_by)},
    )
    booking.status = BookingStatus.cancelled_slot_taken


def _owe_refund(db: Session, admin_id: uuid.UUID, paid: Payment) -> Payment:
    return bookings_service.owe_refund(db, admin_id, paid)


def reject(db: Session, admin_id: uuid.UUID, payment_id: uuid.UUID, reason: str, now: datetime) -> Payment:
    """The money didn't arrive, or the reference is wrong. The parent sees the reason and can send a new
    reference before the deadline; past it, the booking is cancelled at once."""
    payment, booking = _pending_booking_payment(db, payment_id)
    payment.status = PaymentStatus.rejected
    payment.rejection_reason = reason
    payment.confirmed_by = admin_id
    payment.confirmed_at = now
    audit.record(
        db,
        admin_id,
        "payment_rejected",
        "payment",
        str(payment.id),
        before={"status": PaymentStatus.pending.value},
        after={"status": payment.status.value, "booking_id": str(booking.id)},
    )
    db.flush()
    bookings_service.cancel_unpaid(db, now, booking.id)
    if booking.status == BookingStatus.cancelled_parent_late:
        _charge_late_cancellation(db, admin_id, booking, now)
    db.commit()
    return payment


def _charge_late_cancellation(db: Session, admin_id: uuid.UUID, booking: Booking, now: datetime) -> None:
    """The parent cancelled late and the payment they'd sent didn't arrive: the whole booking is still
    charged (6.5), so it's owed as a cancellation charge, which blocks new bookings until paid."""
    covered = db.scalar(
        select(Payment.id).where(
            Payment.booking_id == booking.id,
            Payment.kind.in_((PaymentKind.booking, PaymentKind.cancellation_charge)),
            Payment.status.in_((PaymentStatus.pending, PaymentStatus.confirmed)),
        )
    )
    if covered is not None:
        return
    charge = Payment(
        booking_id=booking.id,
        parent_id=booking.parent_id,
        kind=PaymentKind.cancellation_charge,
        amount_paise=booking.price_paise,
        status=PaymentStatus.pending,
    )
    db.add(charge)
    db.flush()
    audit.record(
        db,
        admin_id,
        "cancellation_charge_owed",
        "payment",
        str(charge.id),
        after={"booking_id": str(booking.id), "amount_paise": charge.amount_paise},
    )


def mark_refunded(
    db: Session, admin_id: uuid.UUID, refund_id: uuid.UUID, transfer_reference: str, now: datetime
) -> Payment:
    """Pacifyco has paid the refund back, recorded with the UPI or bank transfer reference."""
    refund = db.scalar(select(Payment).where(Payment.id == refund_id).with_for_update())
    if refund is None or refund.kind != PaymentKind.refund:
        raise AppError(404, "not_found", "We couldn't find that refund.")
    if refund.status != PaymentStatus.pending:
        raise AppError(409, "refund_already_paid", "This refund has already been marked as paid.")
    reference = transfer_reference.strip()
    if not reference:
        raise AppError(422, "transfer_reference_needed", "Please enter the UPI or bank transfer reference.")
    refund.status = PaymentStatus.confirmed
    refund.confirmed_by = admin_id
    refund.confirmed_at = now
    refund.transfer_reference = reference
    audit.record(
        db,
        admin_id,
        "refund_paid",
        "payment",
        str(refund.id),
        before={"status": PaymentStatus.pending.value},
        after={"status": refund.status.value, "amount_paise": refund.amount_paise},
    )
    db.commit()
    return refund


# Admins are emailed about a booking payment still unchecked this close to its booking's start (Reuben,
# 2026-11-19: "about an hour before"). The frequent job runs every 30 minutes, so the email arrives
# between 60 and 90 minutes before the start (bookings starting before 7:30 am India time are alerted at
# the 6 am run).
ALERT_BEFORE_START = timedelta(minutes=90)
ALERTED = "unchecked_payment_alerted"


@dataclass(frozen=True)
class Unchecked:
    payment_id: uuid.UUID
    booking_id: uuid.UUID
    starts_at: datetime


def unchecked_near_start(db: Session, now: datetime) -> list[Unchecked]:
    """Pending booking payments whose booking (still waiting for that payment) starts within
    `ALERT_BEFORE_START`, or has started, and that admins haven't been alerted to yet."""
    alerted = exists().where(
        AuditLog.action == ALERTED, AuditLog.entity == "payment", AuditLog.entity_id == cast(Payment.id, String)
    )
    rows = db.execute(
        select(Payment.id, Booking.id, Booking.starts_at)
        .join(Booking, Booking.id == Payment.booking_id)
        .where(
            Payment.kind == PaymentKind.booking,
            Payment.status == PaymentStatus.pending,
            Booking.status == BookingStatus.pending_payment,
            Booking.starts_at <= now + ALERT_BEFORE_START,
            ~alerted,
        )
        .order_by(Booking.starts_at)
    )
    return [Unchecked(payment_id, booking_id, starts_at) for payment_id, booking_id, starts_at in rows]


def mark_alerted(db: Session, found: list[Unchecked]) -> None:
    """Remembers each alert (in the audit log), so no payment is alerted twice. The caller commits."""
    for item in found:
        audit.record(db, None, ALERTED, "payment", str(item.payment_id), after={"booking_id": str(item.booking_id)})


def waiting_for_admins(db: Session) -> tuple[list[Payment], list[Payment]]:
    """Payments to check (booking payments, and charges with a reference sent) and refunds still to pay
    back, oldest first."""

    def pending(*conditions) -> list[Payment]:
        return list(
            db.scalars(
                select(Payment).where(Payment.status == PaymentStatus.pending, *conditions).order_by(Payment.created_at)
            )
        )

    to_check = pending(
        or_(
            Payment.kind == PaymentKind.booking,
            and_(Payment.kind.in_(CHARGE_KINDS), Payment.upi_reference.is_not(None)),
        )
    )
    return to_check, pending(Payment.kind == PaymentKind.refund)


# ---------- the parent's payment history (phase 6) ----------


@dataclass(frozen=True)
class HistoryItem:
    payment: Payment
    booking: Booking
    sitter_name: str | None


def history(db: Session, parent_id: uuid.UUID) -> list[HistoryItem]:
    """Every payment, charge and refund of this parent's, newest first."""
    rows = db.execute(
        select(Payment, Booking, Profile.full_name)
        .join(Booking, Booking.id == Payment.booking_id)
        .join(Profile, Profile.id == Booking.sitter_id)
        .where(Payment.parent_id == parent_id)
        .order_by(Payment.created_at.desc(), Payment.id.desc())
    )
    return [HistoryItem(payment, booking, sitter_name) for payment, booking, sitter_name in rows]
