"""Emails about booking requests (CLAUDE.md 6.4; Reuben, 2026-11-19), shared by the routers and the jobs.

Sending never fails what triggered it: the decision is already saved (see `email`)."""

import uuid

from sqlalchemy.orm import Session

from app.models import Booking, PaymentStatus, Profile
from app.services import bookings, payments
from app.services import email as email_service
from app.services.email import EmailClient
from app.settings import LOCAL_WEB_ORIGIN, Settings


def web_url(settings: Settings) -> str:
    return settings.public_web_url or LOCAL_WEB_ORIGIN


def _people(db: Session, booking_id: uuid.UUID) -> tuple[Booking, Profile, Profile]:
    booking = db.get(Booking, booking_id)
    assert booking is not None
    parent = db.get(Profile, booking.parent_id)
    sitter = db.get(Profile, booking.sitter_id)
    assert parent is not None and sitter is not None
    return booking, parent, sitter


def _first(name: str | None) -> str:
    name = (name or "").strip()
    return name.split()[0] if name else "A"


def tell_sitter(db: Session, mailer: EmailClient, settings: Settings, booking_id: uuid.UUID) -> None:
    """A request she can now see."""
    booking, parent, sitter = _people(db, booking_id)
    mailer.send(
        email_service.booking_requested(
            sitter.email,
            sitter.full_name,
            _first(parent.full_name),
            bookings.answer_by(booking),
            booking.id,
            web_url(settings),
        )
    )


def tell_parent_accepted(db: Session, mailer: EmailClient, settings: Settings, booking_id: uuid.UUID) -> None:
    booking, parent, sitter = _people(db, booking_id)
    mailer.send(
        email_service.request_accepted(
            parent.email, parent.full_name, sitter.full_name, bookings.pay_by(booking), booking.id, web_url(settings)
        )
    )


def tell_parent_not_taken(
    db: Session, mailer: EmailClient, settings: Settings, booking_id: uuid.UUID, *, lapsed: bool
) -> None:
    booking, parent, sitter = _people(db, booking_id)
    mailer.send(
        email_service.request_not_taken(
            parent.email, parent.full_name, sitter.full_name, lapsed, booking.id, web_url(settings)
        )
    )


def tell_sitter_cancelled_by_family(
    db: Session, mailer: EmailClient, settings: Settings, booking_id: uuid.UUID
) -> None:
    booking, parent, sitter = _people(db, booking_id)
    mailer.send(
        email_service.cancelled_by_family(
            sitter.email, sitter.full_name, _first(parent.full_name), booking.starts_at, web_url(settings)
        )
    )


def tell_cancelled_by_sitter(
    db: Session, mailer: EmailClient, settings: Settings, booking_id: uuid.UUID, *, late: bool
) -> None:
    """The parent, and the admins so they can look for a replacement (Family Terms 4.7)."""
    booking, parent, sitter = _people(db, booking_id)
    # Money paid, or a UPI reference still being checked, comes back.
    sent = payments.latest_booking_payment(db, booking.id)
    refunded = sent is not None and sent.status != PaymentStatus.rejected
    mailer.send(
        email_service.cancelled_by_sitter(
            parent.email, parent.full_name, sitter.full_name, refunded, booking.id, web_url(settings)
        )
    )
    for to in settings.admin_alert_emails:
        mailer.send(email_service.sitter_cancelled_alert(to, late, booking.starts_at, web_url(settings)))
