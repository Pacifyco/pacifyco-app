"""Emails to parents and sitters, sent through Resend (CLAUDE.md 3). Brought forward from phase 11 on
2026-11-13 (Reuben): approval emails, so people hear when their profile or child is approved.

design.md 2: a 600px single column on Blush with a white card, one primary button, signed "Warmly, the
Pacifyco team". Only a first name and a link: no dates of birth, health or document details.

Swappable in tests via the `get_email` dependency, the same way `get_storage` is. Sending never fails
the request that triggered it: the decision is already saved, so a failed email is logged (and reaches
Sentry) instead."""

import html
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Protocol
from zoneinfo import ZoneInfo

import httpx2 as httpx
from fastapi import Depends

from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)

INDIA = ZoneInfo("Asia/Kolkata")
RESEND_URL = "https://api.resend.com/emails"
REQUEST_TIMEOUT = 10


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    heading: str
    body: str  # plain sentences; escaped when turned into HTML
    button_label: str
    button_url: str


class EmailClient(Protocol):
    def send(self, email: Email) -> None: ...


def render_html(email: Email) -> str:
    text = html.escape
    paragraphs = "".join(
        f'<p style="margin:0 0 16px;font-size:16px;line-height:26px;color:#2D221D">{text(line)}</p>'
        for line in email.body.split("\n")
        if line.strip()
    )
    return (
        "<!doctype html><html>"
        '<body style="margin:0;background:#FFF1E8;font-family:Poppins,Helvetica Neue,Arial,sans-serif">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#FFF1E8">'
        '<tr><td align="center" style="padding:32px 16px">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        'style="max-width:600px;width:100%;background:#FFFFFF;border-radius:24px">'
        '<tr><td style="padding:32px">'
        f'<h1 style="margin:0 0 16px;font-size:24px;line-height:32px;color:#2D221D">{text(email.heading)}</h1>'
        f"{paragraphs}"
        f'<p style="margin:24px 0"><a href="{text(email.button_url)}" '
        'style="display:inline-block;background:#F5695A;color:#2D221D;text-decoration:none;'
        f'padding:12px 24px;border-radius:999px;font-weight:500">{text(email.button_label)}</a></p>'
        '<p style="margin:0;font-size:16px;line-height:26px;color:#2D221D">Warmly, the Pacifyco team</p>'
        "</td></tr></table></td></tr></table></body></html>"
    )


def render_text(email: Email) -> str:
    return f"{email.heading}\n\n{email.body}\n\n{email.button_label}: {email.button_url}\n\nWarmly, the Pacifyco team\n"


class ResendEmail:
    def __init__(self, settings: Settings) -> None:
        self._key = settings.resend_api_key
        self._sender = settings.email_from

    def send(self, email: Email) -> None:
        if not self._key or not self._sender:
            logger.info("Email not sent: RESEND_API_KEY or EMAIL_FROM isn't set")
            return
        try:
            response = httpx.post(
                RESEND_URL,
                headers={"Authorization": f"Bearer {self._key}"},
                json={
                    "from": self._sender,
                    "to": [email.to],
                    "subject": email.subject,
                    "html": render_html(email),
                    "text": render_text(email),
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("Couldn't send an email")  # never the address or the content


def get_email(settings: Annotated[Settings, Depends(get_settings)]) -> EmailClient:
    return ResendEmail(settings)


# ---------- the emails ----------


def _first_name(full_name: str | None) -> str:
    return (full_name or "").strip().split(" ")[0] if full_name and full_name.strip() else "there"


def sitter_approved(to: str, full_name: str | None, web_url: str) -> Email:
    return Email(
        to=to,
        subject="You're approved on Pacifyco",
        heading=f"You're approved, {_first_name(full_name)}.",
        body=(
            "Pacifyco has checked everything you sent, and your profile is now live. "
            "Families near you can find you and book you.\n"
            "Keep your usual week up to date, so families can book you inside the times you're free."
        ),
        button_label="Open Pacifyco",
        button_url=f"{web_url.rstrip('/')}/sitter",
    )


def child_verified(to: str, full_name: str | None, child_name: str, family_verified: bool, web_url: str) -> Email:
    child = child_name.strip().split(" ")[0]
    ending = (
        "Every child on your account is now verified, so your bookings can be confirmed."
        if family_verified
        else "Bookings with your other children are confirmed once theirs are checked too."
    )
    return Email(
        to=to,
        subject=f"{child} is verified on Pacifyco",
        heading=f"{child} is verified.",
        body=(
            f"Hi {_first_name(full_name)}, Pacifyco has checked {child}'s birth certificate and deleted it, "
            f"as promised. We keep only the result.\n{ending}"
        ),
        button_label="Find a sitter",
        button_url=f"{web_url.rstrip('/')}/parent/sitters",
    )


# ---------- rejections (Reuben, 2026-11-13) ----------
# The admin's reason is the one the person also sees in the app (CLAUDE.md 7, "Rejections").

STEP_NAMES = {
    "profile": "your profile",
    "identity_documents": "your ID documents",
    "police_certificate": "your police clearance certificate",
}


def _needs_another_look(to: str, full_name: str | None, what: str, reason: str | None, after: str, url: str) -> Email:
    because = f"The reason: {reason}" if reason else "Please open the app to see what to change."
    return Email(
        to=to,
        subject="Something needs another look on Pacifyco",
        heading=f"{what[0].upper()}{what[1:]} needs another look.",
        body=f"Hi {_first_name(full_name)}, Pacifyco couldn't accept {what}.\n{because}\n{after}",
        button_label="Open Pacifyco",
        button_url=url,
    )


def child_rejected(to: str, full_name: str | None, child_name: str, reason: str | None, web_url: str) -> Email:
    child = child_name.strip().split(" ")[0]
    return _needs_another_look(
        to,
        full_name,
        f"{child}'s birth certificate",
        reason,
        "Please upload a new one from My family.",
        f"{web_url.rstrip('/')}/parent/family",
    )


def sitter_step_rejected(to: str, full_name: str | None, step: str, reason: str | None, web_url: str) -> Email:
    return _needs_another_look(
        to,
        full_name,
        STEP_NAMES.get(step, "a step of your application"),
        reason,
        "Please fix it from Your profile, and Pacifyco will check it again.",
        f"{web_url.rstrip('/')}/sitter/profile",
    )


def reference_rejected(to: str, full_name: str | None, referee: str, reason: str | None, web_url: str) -> Email:
    return _needs_another_look(
        to,
        full_name,
        f"your reference from {referee}",
        reason,
        "Please remove it and add someone else from Your profile.",
        f"{web_url.rstrip('/')}/sitter/profile",
    )


def psych_test_failed(to: str, full_name: str | None, reason: str | None, web_url: str) -> Email:
    return _needs_another_look(
        to,
        full_name,
        "your psychology screening",
        reason,
        "Pacifyco will let you know if you can take it again.",
        f"{web_url.rstrip('/')}/sitter/profile",
    )


def sitter_application_rejected(to: str, full_name: str | None, reason: str | None, web_url: str) -> Email:
    because = f"The reason: {reason}" if reason else "Please open the app to see why."
    return Email(
        to=to,
        subject="About your Pacifyco application",
        heading="We couldn't approve your application.",
        body=(
            f"Hi {_first_name(full_name)}, thank you for applying to Pacifyco. We couldn't approve your "
            f"application this time.\n{because}\nIf you'd like to talk about it, reply to this email."
        ),
        button_label="Open Pacifyco",
        button_url=f"{web_url.rstrip('/')}/sitter/profile",
    )


# ---------- booking payments (phase 6) ----------
# Only first names, the amount and a link to the booking; no dates of birth or other details.


def _booking_url(web_url: str, booking_id: object) -> str:
    return f"{web_url.rstrip('/')}/parent/bookings/{booking_id}"


def _rupees(paise: int) -> str:
    rupees, rest = divmod(abs(paise), 100)
    return f"₹{rupees:,}" + (f".{rest:02d}" if rest else "")


def booking_paid(
    to: str, full_name: str | None, sitter_name: str | None, verified: bool, booking_id: object, web_url: str
) -> Email:
    sitter = _first_name(sitter_name) if sitter_name else "your sitter"
    if verified:
        heading, ending = "Your booking is confirmed.", f"Your time with {sitter} is booked."
    else:
        heading = "We've received your payment."
        ending = (
            "The booking is confirmed once Pacifyco has checked every child's birth certificate. Until then "
            f"the time with {sitter} isn't kept for you: if another booking for it is confirmed first, or the "
            "check isn't done by the start, the booking is cancelled and you're refunded in full."
        )
    return Email(
        to=to,
        subject="Your Pacifyco booking is paid",
        heading=heading,
        body=f"Hi {_first_name(full_name)}, thank you: Pacifyco has received your payment.\n{ending}",
        button_label="See your booking",
        button_url=_booking_url(web_url, booking_id),
    )


def booking_payment_rejected(to: str, full_name: str | None, reason: str, booking_id: object, web_url: str) -> Email:
    return Email(
        to=to,
        subject="We couldn't confirm your Pacifyco payment",
        heading="We couldn't confirm your payment.",
        body=(
            f"Hi {_first_name(full_name)}, Pacifyco couldn't confirm the payment for your booking.\n"
            f"The reason: {reason}\n"
            "Please check the UPI reference and send it again from your booking before the time to pay ends."
        ),
        button_label="Open your booking",
        button_url=_booking_url(web_url, booking_id),
    )


def booking_slot_taken(
    to: str, full_name: str | None, sitter_name: str | None, paid: bool, booking_id: object, web_url: str
) -> Email:
    sitter = _first_name(sitter_name) if sitter_name else "your sitter"
    refund = "\nYou've paid for it, so Pacifyco will refund you in full." if paid else ""
    return Email(
        to=to,
        subject="Your Pacifyco booking was cancelled",
        heading="This time has been taken.",
        body=(
            f"Hi {_first_name(full_name)}, another booking with {sitter} for the same time was confirmed first, "
            f"so yours was cancelled.{refund}\nYou can choose another time with her."
        ),
        button_label="Open your booking",
        button_url=_booking_url(web_url, booking_id),
    )


def unchecked_payments_alert(to: str, count: int, earliest_start: datetime, web_url: str) -> Email:
    """To an admin: payments to check before their bookings start. No names or amounts, only the count
    and the earliest start."""
    local = earliest_start.astimezone(INDIA)
    when = f"{local:%a} {local.day} {local:%b}, {_clock(local)}"
    payments = "1 payment" if count == 1 else f"{count} payments"
    return Email(
        to=to,
        subject=f"{payments} to check before the booking starts",
        heading=f"{payments} still to check.",
        body=(
            f"A parent has sent a UPI reference and the booking starts soon: the first at {when}.\n"
            "Please confirm or reject it on the Payments page before then. A booking whose start has "
            "passed can't be confirmed."
        ),
        button_label="Check payments",
        button_url=f"{web_url.rstrip('/')}/admin/payments",
    )


def _clock(moment: datetime) -> str:
    hour = moment.hour % 12 or 12
    return f"{hour}:{moment.minute:02d} {'am' if moment.hour < 12 else 'pm'}"


def refund_paid(to: str, full_name: str | None, amount_paise: int, booking_id: object, web_url: str) -> Email:
    return Email(
        to=to,
        subject="Pacifyco has refunded you",
        heading=f"We've refunded {_rupees(amount_paise)}.",
        body=(
            f"Hi {_first_name(full_name)}, Pacifyco has paid back {_rupees(amount_paise)} for your cancelled "
            "booking. It can take a little while to show in your account."
        ),
        button_label="Open your booking",
        button_url=_booking_url(web_url, booking_id),
    )
