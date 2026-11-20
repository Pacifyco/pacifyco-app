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


def tell_removed_for_strikes(db: Session, mailer: EmailClient, settings: Settings, sitter_id: uuid.UUID) -> None:
    """Her 5th strike removed her account: tell her, and the admins (her bookings need looking at)."""
    sitter = db.get(Profile, sitter_id)
    assert sitter is not None
    mailer.send(email_service.removed_for_strikes(sitter.email, sitter.full_name))
    for to in settings.admin_alert_emails:
        mailer.send(email_service.sitter_removed_alert(to, sitter.full_name, web_url(settings), sitter_id))


def tell_reported(db: Session, mailer: EmailClient, settings: Settings, report) -> None:
    """A report was made: the admins (to phone both), and the other side."""
    booking, parent, sitter = _people(db, report.booking_id)
    url = web_url(settings)
    for to in settings.admin_alert_emails:
        mailer.send(email_service.report_alert(to, report.kind.value, booking.starts_at, url))
    if report.kind.value == "parent_absent":
        mailer.send(
            email_service.sitter_at_your_home(parent.email, parent.full_name, sitter.full_name, booking.id, url)
        )
    elif report.kind.value == "only_man_home":
        mailer.send(
            email_service.sitter_declined_man_home(parent.email, parent.full_name, sitter.full_name, booking.id, url)
        )
    else:
        mailer.send(
            email_service.no_show_reported(
                sitter.email, sitter.full_name, _first(parent.full_name), booking.starts_at, url
            )
        )


def tell_decided(db: Session, mailer: EmailClient, settings: Settings, report, fee_paise: int) -> None:
    """An admin confirmed or dismissed a report: both people hear the outcome."""
    booking, parent, sitter = _people(db, report.booking_id)
    url = web_url(settings)
    parent_url = f"{url.rstrip('/')}/parent/bookings/{booking.id}"
    sitter_url = f"{url.rstrip('/')}/sitter/bookings/{booking.id}"
    confirmed = report.status.value == "confirmed"
    rupees = f"₹{fee_paise // 100:,}"
    if report.kind.value == "parent_absent":
        if confirmed:
            parent_says = (
                "Your booking was closed: no one was home",
                "no one was home when your sitter arrived, so the booking is closed and the whole booking is charged.",
            )
            sitter_says = (
                "Your show-up fee is confirmed",
                f"Pacifyco confirmed no one was home. You'll be paid a show-up fee of {rupees}.",
            )
        else:
            parent_says = (
                "Your booking goes ahead",
                "Pacifyco has looked at your sitter's report: the booking goes ahead.",
            )
            sitter_says = (
                "Your report was looked at",
                "Pacifyco has looked at your report and won't close the booking.",
            )
    elif report.kind.value == "only_man_home":
        if confirmed:
            parent_says = (
                "Your booking was closed",
                "your sitter declined because the only adult at home was a "
                "man, so the booking is closed and the whole booking is charged.",
            )
            sitter_says = (
                "Pacifyco confirmed your report",
                f"thank you for keeping yourself safe. You won't get a strike, and you'll be paid {rupees}.",
            )
        else:
            parent_says = ("Your report was looked at", "Pacifyco has looked at your sitter's report and dismissed it.")
            sitter_says = ("Your report was looked at", "Pacifyco has looked at your report and dismissed it.")
    elif confirmed:
        parent_says = (
            "We're sorry: your sitter didn't come",
            "Pacifyco confirmed your sitter didn't come. You'll be refunded in full.",
        )
        sitter_says = (
            "A missed booking was confirmed",
            "Pacifyco confirmed you didn't arrive for a booking. It counts as a strike, and you aren't paid for it.",
        )
    else:
        parent_says = ("Your report was looked at", "Pacifyco has looked at your report and won't close the booking.")
        sitter_says = ("A report about you was dismissed", "Pacifyco looked at the family's report and dismissed it.")
    mailer.send(
        email_service.report_decided(parent.email, parent.full_name, *parent_says, "Open your booking", parent_url)
    )
    mailer.send(
        email_service.report_decided(sitter.email, sitter.full_name, *sitter_says, "Open the booking", sitter_url)
    )
