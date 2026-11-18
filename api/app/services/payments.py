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
from datetime import datetime
from urllib.parse import quote, urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Booking, BookingStatus, Payment, PaymentKind, PaymentStatus, Profile
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


def payment_instructions(upi_id: str, booking: Booking) -> PaymentInstructions | None:
    """How to pay for this booking, or None while Pacifyco's UPI ID isn't set."""
    if not upi_id:
        return None
    note = booking_note(booking.id)
    params = {
        "pa": upi_id,
        "pn": PAYEE_NAME,
        "am": f"{booking.price_paise // 100}.{booking.price_paise % 100:02d}",
        "cu": "INR",
        "tn": note,
    }
    link = "upi://pay?" + urlencode(params, quote_via=quote, safe="@")
    return PaymentInstructions(upi_id, PAYEE_NAME, booking.price_paise, note, link)


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
    # Lock the booking so two submissions at once can't both add a payment.
    db.scalar(select(Booking.id).where(Booking.id == booking.id).with_for_update())
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
