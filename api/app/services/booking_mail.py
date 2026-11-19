"""Emails about booking requests (CLAUDE.md 6.4; Reuben, 2026-11-19), shared by the routers and the jobs.

Sending never fails what triggered it: the decision is already saved (see `email`)."""

import uuid

from sqlalchemy.orm import Session

from app.models import Booking, Profile
from app.services import bookings
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
