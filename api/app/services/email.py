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
UNDELIVERABLE = "@example.com"  # RFC 2606: reserved, never delivered


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
        if email.to.lower().endswith(UNDELIVERABLE):
            # Reserved, never a real inbox: staging's seeded people (staging_seed.py). Sending would only
            # bounce and log an error.
            logger.info("Email not sent: the address is a reserved example one")
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


def _when(moment: datetime) -> str:
    local = moment.astimezone(INDIA)
    return f"{local:%a} {local.day} {local:%b}, {_clock(local)}"


def booking_requested(
    to: str, full_name: str | None, family_name: str, answer_by: datetime, booking_id: object, web_url: str
) -> Email:
    """To the sitter: a request she can now see (every child on it verified)."""
    return Email(
        to=to,
        subject="A new booking request on Pacifyco",
        heading="You have a new booking request.",
        body=(
            f"Hi {_first_name(full_name)}, {family_name}'s family would like to book you.\n"
            f"Please accept or decline by {_when(answer_by)}. After that the request lapses."
        ),
        button_label="See the request",
        button_url=f"{web_url.rstrip('/')}/sitter/bookings/{booking_id}",
    )


def request_accepted(
    to: str, full_name: str | None, sitter_name: str | None, pay_by: datetime, booking_id: object, web_url: str
) -> Email:
    sitter = _first_name(sitter_name) if sitter_name else "Your sitter"
    return Email(
        to=to,
        subject="Your sitter has accepted: please pay to confirm",
        heading=f"{sitter} has accepted your booking.",
        body=(
            f"Hi {_first_name(full_name)}, {sitter} can look after your children. Her time is held for you.\n"
            f"Please pay by {_when(pay_by)} to confirm the booking. If it isn't paid by then, it's cancelled."
        ),
        button_label="Pay for your booking",
        button_url=_booking_url(web_url, booking_id),
    )


def request_not_taken(
    to: str, full_name: str | None, sitter_name: str | None, lapsed: bool, booking_id: object, web_url: str
) -> Email:
    """The request was declined, or lapsed unanswered. Nothing was paid."""
    sitter = _first_name(sitter_name) if sitter_name else "The sitter"
    what = f"{sitter} didn't answer your request in time" if lapsed else f"{sitter} can't take your booking"
    return Email(
        to=to,
        subject="Your booking request wasn't accepted",
        heading=f"{what}.",
        body=(
            f"Hi {_first_name(full_name)}, {what}, so the request has closed. You haven't been charged.\n"
            "You can book another sitter for the same time."
        ),
        button_label="Find a sitter",
        button_url=f"{web_url.rstrip('/')}/parent/sitters",
    )


def cancelled_by_family(to: str, full_name: str | None, family_name: str, starts_at: datetime, web_url: str) -> Email:
    """To the sitter: a booking she had accepted was cancelled by the family."""
    return Email(
        to=to,
        subject="A booking was cancelled",
        heading="A family has cancelled a booking.",
        body=(
            f"Hi {_first_name(full_name)}, {family_name}'s family has cancelled their booking for "
            f"{_when(starts_at)}. That time is free again for other families."
        ),
        button_label="See your bookings",
        button_url=f"{web_url.rstrip('/')}/sitter/bookings",
    )


def cancelled_by_sitter(
    to: str, full_name: str | None, sitter_name: str | None, refunded: bool, booking_id: object, web_url: str
) -> Email:
    """To the parent: the sitter can't make it."""
    sitter = _first_name(sitter_name) if sitter_name else "Your sitter"
    money = "Pacifyco will refund you in full.\n" if refunded else "You haven't been charged.\n"
    return Email(
        to=to,
        subject="Your sitter had to cancel",
        heading=f"{sitter} had to cancel your booking.",
        body=(
            f"Hi {_first_name(full_name)}, we're sorry: {sitter} can't make your booking, so it's cancelled.\n"
            f"{money}Pacifyco will try to find you another sitter, or you can book one yourself."
        ),
        button_label="Find a sitter",
        button_url=f"{web_url.rstrip('/')}/parent/sitters",
    )


def sitter_cancelled_alert(to: str, late: bool, starts_at: datetime, web_url: str) -> Email:
    """To an admin: a sitter cancelled, so the family may need a replacement (Family Terms 4.7)."""
    when = "less than 8 hours" if late else "8 hours or more"
    return Email(
        to=to,
        subject="A sitter cancelled a booking",
        heading="A sitter cancelled a booking.",
        body=(
            f"A sitter cancelled a booking starting {_when(starts_at)}, {when} before the start"
            f"{' (a late cancellation: she has a strike)' if late else ''}.\n"
            "The family has been told. Please try to find them another sitter, and pay any refund back."
        ),
        button_label="Open the admin panel",
        button_url=f"{web_url.rstrip('/')}/admin",
    )


def strike_given(
    to: str, full_name: str | None, note: str | None, blocked_until: datetime | None, web_url: str
) -> Email:
    """To the sitter: an admin gave her a strike (6.6)."""
    block = f"You can't take new bookings until {_when(blocked_until)}.\n" if blocked_until else ""
    reason = f"The reason: {note}\n" if note else ""
    return Email(
        to=to,
        subject="You have a strike on Pacifyco",
        heading="Pacifyco has given you a strike.",
        body=f"Hi {_first_name(full_name)}, {reason}{block}A strike counts for 6 months. Your confirmed bookings stay.",
        button_label="See your strikes",
        button_url=f"{web_url.rstrip('/')}/sitter/strikes",
    )


def strike_removed(to: str, full_name: str | None, reason: str, web_url: str) -> Email:
    return Email(
        to=to,
        subject="A strike has been removed",
        heading="Pacifyco has removed a strike.",
        body=f"Hi {_first_name(full_name)}, Pacifyco has removed one of your strikes.\nThe reason: {reason}",
        button_label="See your strikes",
        button_url=f"{web_url.rstrip('/')}/sitter/strikes",
    )


def removed_for_strikes(to: str, full_name: str | None) -> Email:
    """To the sitter: the 5th strike in 6 months removes her account (6.6)."""
    return Email(
        to=to,
        subject="Your Pacifyco account has been removed",
        heading="Your account has been removed.",
        body=(
            f"Hi {_first_name(full_name)}, you've had five strikes in 6 months, so your Pacifyco account has been "
            "removed and you can't take bookings.\nIf you think this is wrong, please write to founders@pacifyco.in."
        ),
        button_label="Contact Pacifyco",
        button_url="mailto:founders@pacifyco.in",
    )


def sitter_removed_alert(to: str, sitter_name: str | None, web_url: str, sitter_id: object) -> Email:
    """To an admin: a sitter was removed after a 5th strike; her confirmed bookings need looking at."""
    return Email(
        to=to,
        subject="A sitter was removed after a fifth strike",
        heading="A sitter was removed after a fifth strike.",
        body=(
            f"{sitter_name or 'A sitter'} has had five strikes in 6 months, so her account was removed.\n"
            "Please check her confirmed bookings: the families may need another sitter."
        ),
        button_label="Open her profile",
        button_url=f"{web_url.rstrip('/')}/admin/sitters/{sitter_id}",
    )


def _charge_url(web_url: str, payment_id: object) -> str:
    return f"{web_url.rstrip('/')}/parent/payments/{payment_id}"


def charge_paid(to: str, full_name: str | None, amount_paise: int, payment_id: object, web_url: str) -> Email:
    return Email(
        to=to,
        subject="Your Pacifyco payment is confirmed",
        heading=f"We've received your {_rupees(amount_paise)}.",
        body=f"Hi {_first_name(full_name)}, thank you: Pacifyco has received your payment. You can book again.",
        button_label="Find a sitter",
        button_url=f"{web_url.rstrip('/')}/parent/sitters",
    )


def charge_reference_rejected(to: str, full_name: str | None, reason: str, payment_id: object, web_url: str) -> Email:
    return Email(
        to=to,
        subject="We couldn't confirm your Pacifyco payment",
        heading="We couldn't confirm your payment.",
        body=(
            f"Hi {_first_name(full_name)}, Pacifyco couldn't confirm your payment.\nThe reason: {reason}\n"
            "Please check the UPI reference and send it again."
        ),
        button_label="Open the payment",
        button_url=_charge_url(web_url, payment_id),
    )


def report_alert(to: str, kind: str, starts_at: datetime, web_url: str) -> Email:
    """To an admin: a report to act on now (6.5): phone both people."""
    what = {
        "parent_absent": "A sitter says no one is home",
        "only_man_home": "A sitter declined: the only adult at home is a man",
        "child_under_age": "A sitter says a child is under 18 months",
        "sitter_unsafe": "A sitter left a booking for her own safety",
    }.get(kind, "A parent says their sitter didn't come")
    return Email(
        to=to,
        subject=f"{what}",
        heading=f"{what}.",
        body=(
            f"For the booking that started {_when(starts_at)}. Please call both of them now, then confirm or "
            "dismiss the report."
        ),
        button_label="Open the reports",
        button_url=f"{web_url.rstrip('/')}/admin/reports",
    )


def sitter_at_your_home(
    to: str, full_name: str | None, sitter_name: str | None, booking_id: object, web_url: str
) -> Email:
    """To the parent: the sitter is there and can't find anyone (6.5)."""
    sitter = _first_name(sitter_name) if sitter_name else "Your sitter"
    return Email(
        to=to,
        subject="Your sitter is at your home",
        heading=f"{sitter} is at your home and can't find you.",
        body=(
            f"Hi {_first_name(full_name)}, {sitter} has arrived but no one is home. If you're on your way, open your "
            "booking and press I have arrived, or call Pacifyco. If no one responds within 20 minutes she may leave, "
            "and the whole booking is charged."
        ),
        button_label="Open your booking",
        button_url=_booking_url(web_url, booking_id),
    )


def sitter_declined_man_home(
    to: str, full_name: str | None, sitter_name: str | None, booking_id: object, web_url: str
) -> Email:
    """To the parent: she declined on arrival because the only adult at home was a man (6.5)."""
    sitter = _first_name(sitter_name) if sitter_name else "Your sitter"
    return Email(
        to=to,
        subject="Your sitter declined the booking",
        heading=f"{sitter} declined the booking.",
        body=(
            f"Hi {_first_name(full_name)}, {sitter} declined the booking because the only adult at home was a man. "
            "As the Family Terms say, a sitter may do this for her safety, and the whole booking is charged.\n"
            "Pacifyco will be in touch."
        ),
        button_label="Open your booking",
        button_url=_booking_url(web_url, booking_id),
    )


def sitter_reported_under_age(
    to: str, full_name: str | None, sitter_name: str | None, booking_id: object, web_url: str
) -> Email:
    """To the parent: a child on this booking turned out to be under 18 months (6.5)."""
    sitter = _first_name(sitter_name) if sitter_name else "Your sitter"
    return Email(
        to=to,
        subject="Your sitter ended the booking",
        heading=f"{sitter} ended the booking.",
        body=(
            f"Hi {_first_name(full_name)}, {sitter} says a child on this booking is under 18 months, which "
            "Pacifyco doesn't take bookings for. She isn't required to care for them. You're charged for 1 hour "
            "and the rest is refunded.\nPacifyco will be in touch."
        ),
        button_label="Open your booking",
        button_url=_booking_url(web_url, booking_id),
    )


def sitter_left_unsafe(
    to: str, full_name: str | None, sitter_name: str | None, booking_id: object, web_url: str
) -> Email:
    """To the parent: the sitter had to leave for her own safety, once the child was with you (6.5)."""
    sitter = _first_name(sitter_name) if sitter_name else "Your sitter"
    return Email(
        to=to,
        subject="Your sitter had to leave",
        heading=f"{sitter} had to leave.",
        body=(
            f"Hi {_first_name(full_name)}, {sitter} left this booking for her own safety, once the child was "
            "with you. As usual, the whole booking is charged.\nPacifyco will be in touch."
        ),
        button_label="Open your booking",
        button_url=_booking_url(web_url, booking_id),
    )


def no_show_reported(to: str, full_name: str | None, family_name: str, starts_at: datetime, web_url: str) -> Email:
    """To the sitter: the family says she didn't come."""
    return Email(
        to=to,
        subject="A family says you didn't arrive",
        heading="A family says you didn't arrive.",
        body=(
            f"Hi {_first_name(full_name)}, {family_name}'s family says you didn't arrive for the booking that started "
            f"{_when(starts_at)}. Pacifyco will call you. If it's confirmed it counts as a missed booking: a strike."
        ),
        button_label="See your bookings",
        button_url=f"{web_url.rstrip('/')}/sitter/bookings",
    )


def report_decided(
    to: str, full_name: str | None, heading: str, body: str, button_label: str, button_url: str
) -> Email:
    return Email(
        to=to,
        subject=heading,
        heading=heading,
        body=f"Hi {_first_name(full_name)}, {body}",
        button_label=button_label,
        button_url=button_url,
    )


INCIDENT_WORDS = {
    "emergency": "an emergency",
    "theft": "a theft",
    "abuse": "abuse",
    "sitter_unsafe": "the sitter being abused or feeling unsafe",
}


def incident_alert(to: str, kind: str, by: str, suspended: bool, web_url: str) -> Email:
    """To every admin, at once (6.9): phone both people."""
    what = INCIDENT_WORDS.get(kind, "an emergency")
    return Email(
        to=to,
        subject=f"EMERGENCY on a Pacifyco booking: {what}",
        heading=f"A {by} has reported {what}.",
        body=(
            "Please call both of them now, then acknowledge it in the admin panel."
            + ("\nThe sitter's account has been suspended until you resolve it." if suspended else "")
        ),
        button_label="Open the emergencies",
        button_url=f"{web_url.rstrip('/')}/admin/incidents",
    )


def issue_alert(to: str, topic_words: str, by: str, complaint_url: str) -> Email:
    """To admins: a non-emergency issue on a booking (6.9), a complaint with the usual targets (6.12)."""
    return Email(
        to=to,
        subject=f"An issue on a Pacifyco booking: {topic_words.lower()}",
        heading=f"A {by} has raised an issue.",
        body=f"{topic_words}. Please reply within 24 hours and aim to resolve it within 48.",
        button_label="Open the complaint",
        button_url=complaint_url,
    )


def sitter_suspended(to: str, full_name: str | None) -> Email:
    """To the sitter: a report has suspended her account until an admin looks into it (6.9)."""
    return Email(
        to=to,
        subject="Your Pacifyco account is suspended",
        heading="Your account is suspended for now.",
        body=(
            f"Hi {_first_name(full_name)}, a family has made a serious report about a booking, so your account is "
            "suspended while Pacifyco looks into it. We'll be in touch. If you need to reach us, write to "
            "founders@pacifyco.in."
        ),
        button_label="Contact Pacifyco",
        button_url="mailto:founders@pacifyco.in",
    )


def sitter_reinstated(to: str, full_name: str | None, web_url: str) -> Email:
    return Email(
        to=to,
        subject="Your Pacifyco account is active again",
        heading="Your account is active again.",
        body=f"Hi {_first_name(full_name)}, Pacifyco has looked into the report and your account is active again.",
        button_label="Open Pacifyco",
        button_url=f"{web_url.rstrip('/')}/sitter",
    )


def outing_changed(
    to: str,
    full_name: str | None,
    family_name: str,
    where: str | None,
    starts_at: datetime,
    booking_id: object,
    web_url: str,
) -> Email:
    """To the sitter: the family added, changed or removed an outing on a booking she accepted."""
    what = (
        f"they'll be out: {where}. Meet them there; they'll send the exact address in the chat."
        if where
        else "they've removed the outing, so the booking is at their home."
    )
    return Email(
        to=to,
        subject="A booking's outing has changed",
        heading="The family has changed the outing.",
        body=f"Hi {_first_name(full_name)}, for {family_name}'s booking on {_when(starts_at)}, {what}",
        button_label="See the booking",
        button_url=f"{web_url.rstrip('/')}/sitter/bookings/{booking_id}",
    )


def payouts_due_soon_alert(to: str, count: int, earliest_due: datetime, web_url: str) -> Email:
    """To an admin: payouts with under 3 hours left (6.10). Counts only: no names, amounts or bank details."""
    payouts = "1 payout" if count == 1 else f"{count} payouts"
    return Email(
        to=to,
        subject=f"{payouts} due within 3 hours",
        heading=f"{payouts} due soon.",
        body=(
            f"The first is due by {_when(earliest_due)}. Sitters must be paid within 12 hours, so please pay "
            "and mark it paid on the Payouts page before then."
        ),
        button_label="Open payouts",
        button_url=f"{web_url.rstrip('/')}/admin/payouts",
    )


def payouts_overdue_alert(to: str, count: int, web_url: str) -> Email:
    """To an admin: payouts past their 12-hour deadline (6.10). Counts only."""
    payouts = "1 payout is" if count == 1 else f"{count} payouts are"
    return Email(
        to=to,
        subject=f"{payouts} overdue",
        heading=f"{payouts} past the 12-hour deadline.",
        body="Sitters must be paid within 12 hours. Please pay them now and mark them paid on the Payouts page.",
        button_label="Open payouts",
        button_url=f"{web_url.rstrip('/')}/admin/payouts",
    )


def payout_paid(to: str, full_name: str | None, amount_paise: int, method: str, web_url: str) -> Email:
    """To the sitter: we've paid her (6.10). No account details."""
    how = "by UPI" if method == "upi" else "to your bank account"
    return Email(
        to=to,
        subject=f"We've paid you {_rupees(amount_paise)}",
        heading=f"We've paid you {_rupees(amount_paise)}.",
        body=f"Hi {_first_name(full_name)}, we've sent it {how}. Thank you for your work with Pacifyco.",
        button_label="Open Pacifyco",
        button_url=f"{web_url.rstrip('/')}/sitter",
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


def codes_locked_alert(to: str, which: str, starts_at: datetime, web_url: str) -> Email:
    """To an admin: 5 wrong codes were entered for a booking (6.7). No names; the admin looks it up and
    calls both people."""
    return Email(
        to=to,
        subject="A booking's codes are locked",
        heading=f"Too many wrong {which} codes.",
        body=(
            f"For the booking that started {_when(starts_at)}. Code entry is now locked for it. Please call "
            "both people and close the booking once you know what happened."
        ),
        button_label="Open the admin panel",
        button_url=f"{web_url.rstrip('/')}/admin",
    )


def overdue_checkout_alert(to: str, starts_at: datetime, ends_at: datetime, web_url: str) -> Email:
    """To an admin: a booking is still in progress 30+ minutes past its end (6.7). No names; the admin
    looks it up and calls both people."""
    return Email(
        to=to,
        subject="A booking's check-out is overdue",
        heading="A check-out is overdue.",
        body=(
            f"For the booking that ran {_when(starts_at)} to {_clock(ends_at.astimezone(INDIA))}. It still hasn't "
            "been checked out. Please call both people and close the booking once you know what happened."
        ),
        button_label="Open the admin panel",
        button_url=f"{web_url.rstrip('/')}/admin",
    )


def overtime_requested(
    to: str, full_name: str | None, family_name: str, hours: int, booking_id: object, web_url: str
) -> Email:
    """To the sitter: the parent has asked to stay longer (6.8). Nothing is charged until check-out."""
    plural = "hour" if hours == 1 else "hours"
    return Email(
        to=to,
        subject="A family would like you to stay longer",
        heading=f"{family_name}'s family has asked for {hours} more {plural}.",
        body=(
            f"Hi {_first_name(full_name)}, please accept or decline once you've agreed it between you. "
            "Nothing is charged now; it's worked out when you check out."
        ),
        button_label="Open the booking",
        button_url=f"{web_url.rstrip('/')}/sitter/bookings/{booking_id}",
    )


def overtime_decided(
    to: str,
    full_name: str | None,
    sitter_name: str | None,
    accepted: bool,
    hours: int,
    booking_id: object,
    web_url: str,
) -> Email:
    """To the parent: whether the sitter can stay the extra time (6.8)."""
    sitter = _first_name(sitter_name) if sitter_name else "Your sitter"
    plural = "hour" if hours == 1 else "hours"
    if accepted:
        heading = f"{sitter} can stay {hours} more {plural}."
        body = "Nothing is charged now; it's worked out when the booking ends."
    else:
        heading = f"{sitter} can't stay longer."
        body = "Please plan to be back by the booked end time."
    return Email(
        to=to,
        subject=heading,
        heading=heading,
        body=f"Hi {_first_name(full_name)}, {body}",
        button_label="Open your booking",
        button_url=_booking_url(web_url, booking_id),
    )


def overtime_charged(
    to: str, full_name: str | None, amount_paise: int, hours: int, payment_id: object, web_url: str
) -> Email:
    """To the parent: overtime was worked out at check-out (6.8), payable within 2 hours."""
    plural = "hour" if hours == 1 else "hours"
    return Email(
        to=to,
        subject="You owe Pacifyco for overtime",
        heading=f"{hours} {plural} of overtime: {_rupees(amount_paise)}.",
        body=(
            f"Hi {_first_name(full_name)}, the booking ran {hours} {plural} past its booked end. "
            "Please pay within 2 hours; you can't make new bookings until it's paid."
        ),
        button_label="Pay now",
        button_url=_charge_url(web_url, payment_id),
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


def rating_flag_alert(to: str, sitter_name: str | None, average: str, count: int, web_url: str) -> Email:
    """To an admin: a sitter's last-10 average is below 3.5 (6.11)."""
    who = sitter_name or "A sitter"
    return Email(
        to=to,
        subject="A sitter's ratings are low",
        heading=f"{who}'s average is {average} over her last {count} reviews.",
        body=(
            "That's below 3.5, so she's flagged for review. Before any decision, tell her the reason and give her "
            "a chance to respond."
        ),
        button_label="Open low ratings",
        button_url=f"{web_url.rstrip('/')}/admin/ratings",
    )


def rating_flag_told(to: str, full_name: str | None, reason: str, web_url: str) -> Email:
    """To the sitter: why her ratings are being reviewed, and that she can respond (6.11)."""
    return Email(
        to=to,
        subject="Your ratings are being reviewed",
        heading="Pacifyco is reviewing your ratings.",
        body=(
            f"Hi {_first_name(full_name)}, your recent ratings from families are low, so Pacifyco is reviewing "
            f"them.\nThe reason: {reason}\nPlease tell us your side in the app within 12 hours. We'll read it "
            "before we decide anything."
        ),
        button_label="Respond",
        button_url=f"{web_url.rstrip('/')}/sitter/reviews",
    )


def rating_flag_response_alert(to: str, sitter_name: str | None, web_url: str) -> Email:
    """To an admin: the flagged sitter has responded (6.11)."""
    who = sitter_name or "The sitter"
    return Email(
        to=to,
        subject="A sitter has responded about her ratings",
        heading=f"{who} has responded about her ratings.",
        body="Read her response and close the flag with your decision.",
        button_label="Open low ratings",
        button_url=f"{web_url.rstrip('/')}/admin/ratings",
    )


# ---------- suspending, removing and reinstating accounts (phase 10, Reuben 2026-11-22) ----------

APPEAL = (
    "If you think this is wrong, you can appeal within 15 days of this email: sign in to Pacifyco and send your "
    "appeal there, or write to founders@pacifyco.in. An admin who wasn't part of this decision will look at it."
)


def account_suspended(to: str, full_name: str | None, reason: str) -> Email:
    """To the person: an admin suspended their account, with the reason."""
    return Email(
        to=to,
        subject="Your Pacifyco account is suspended",
        heading="Your account is suspended.",
        body=(
            f"Hi {_first_name(full_name)}, Pacifyco has suspended your account, so you can't use Pacifyco for now. "
            "Any bookings you had coming up have been cancelled, and any money paid for them will be refunded.\n"
            f"The reason: {reason}\n{APPEAL}"
        ),
        button_label="Contact Pacifyco",
        button_url="mailto:founders@pacifyco.in",
    )


def account_removed(to: str, full_name: str | None, reason: str) -> Email:
    """To the person: an admin removed their account, with the reason."""
    return Email(
        to=to,
        subject="Your Pacifyco account has been removed",
        heading="Your account has been removed.",
        body=(
            f"Hi {_first_name(full_name)}, Pacifyco has removed your account, so you can't use Pacifyco any more. "
            "Any bookings you had coming up have been cancelled, and any money paid for them will be refunded.\n"
            f"The reason: {reason}\n{APPEAL}"
        ),
        button_label="Contact Pacifyco",
        button_url="mailto:founders@pacifyco.in",
    )


def account_reinstated(to: str, full_name: str | None, reason: str, area_url: str) -> Email:
    """To the person: an admin made their account usable again."""
    return Email(
        to=to,
        subject="Your Pacifyco account is active again",
        heading="Your account is active again.",
        body=f"Hi {_first_name(full_name)}, Pacifyco has reinstated your account, so you can use Pacifyco again.\n"
        f"{reason}",
        button_label="Open Pacifyco",
        button_url=area_url,
    )


def booking_cancelled_by_pacifyco_for_parent(
    to: str, full_name: str | None, sitter_name: str | None, starts_at: datetime, refunded: bool, web_url: str
) -> Email:
    """To the parent: Pacifyco cancelled a booking because of the sitter's account. No reason is given."""
    sitter = _first_name(sitter_name) if sitter_name else "your sitter"
    money = "Pacifyco will refund you in full." if refunded else "You haven't been charged."
    return Email(
        to=to,
        subject="Pacifyco has cancelled your booking",
        heading="Your booking has been cancelled.",
        body=(
            f"Hi {_first_name(full_name)}, we're sorry: Pacifyco has had to cancel your booking with {sitter} "
            f"for {_when(starts_at)}, as she can't take bookings for now.\n"
            f"{money} Pacifyco will try to find you another sitter, or you can book one yourself."
        ),
        button_label="Find a sitter",
        button_url=f"{web_url.rstrip('/')}/parent/sitters",
    )


def booking_cancelled_by_pacifyco_for_sitter(
    to: str, full_name: str | None, starts_at: datetime, web_url: str
) -> Email:
    """To the sitter: Pacifyco cancelled a booking because of the family's account. No reason is given."""
    return Email(
        to=to,
        subject="A booking was cancelled",
        heading="Pacifyco has cancelled a booking.",
        body=(
            f"Hi {_first_name(full_name)}, Pacifyco has cancelled the booking for {_when(starts_at)}. "
            "That time is free again for other families. There's no strike for you."
        ),
        button_label="See your bookings",
        button_url=f"{web_url.rstrip('/')}/sitter/bookings",
    )


def sitter_bookings_cancelled_alert(to: str, count: int, web_url: str) -> Email:
    """To an admin: a sitter's upcoming bookings were cancelled with her account; families may need
    another sitter. Counts only."""
    bookings = "1 booking" if count == 1 else f"{count} bookings"
    return Email(
        to=to,
        subject="Families need another sitter",
        heading="Families may need another sitter.",
        body=(
            f"A sitter's account was suspended or removed, so {bookings} with her were cancelled and the families "
            "told. Please try to find them another sitter, and pay any refunds back."
        ),
        button_label="Open the admin panel",
        button_url=f"{web_url.rstrip('/')}/admin",
    )


# ---------- an admin's adjustments to a booking (phase 10, Reuben 2026-11-23) ----------


def booking_cancelled_by_admin_for_parent(
    to: str,
    full_name: str | None,
    sitter_name: str | None,
    starts_at: datetime,
    refunded: bool,
    reason: str,
    web_url: str,
) -> Email:
    """To the parent: an admin cancelled a booking, with the reason."""
    sitter = _first_name(sitter_name) if sitter_name else "your sitter"
    money = "Pacifyco will refund you in full." if refunded else "You haven't been charged."
    return Email(
        to=to,
        subject="Pacifyco has cancelled your booking",
        heading="Your booking has been cancelled.",
        body=(
            f"Hi {_first_name(full_name)}, Pacifyco has cancelled your booking with {sitter} for {_when(starts_at)}.\n"
            f"The reason: {reason}\n{money}"
        ),
        button_label="See your bookings",
        button_url=f"{web_url.rstrip('/')}/parent/bookings",
    )


def booking_cancelled_by_admin_for_sitter(
    to: str, full_name: str | None, starts_at: datetime, reason: str, web_url: str
) -> Email:
    """To the sitter: an admin cancelled a booking she had accepted or could see, with the reason."""
    return Email(
        to=to,
        subject="A booking was cancelled",
        heading="Pacifyco has cancelled a booking.",
        body=(
            f"Hi {_first_name(full_name)}, Pacifyco has cancelled the booking for {_when(starts_at)}. "
            f"That time is free again for other families. There's no strike for you.\nThe reason: {reason}"
        ),
        button_label="See your bookings",
        button_url=f"{web_url.rstrip('/')}/sitter/bookings",
    )


def partial_refund(to: str, full_name: str | None, amount_paise: int, reason: str, web_url: str) -> Email:
    """To the parent: an admin is refunding part of what they paid for a booking."""
    return Email(
        to=to,
        subject="Pacifyco is refunding you",
        heading=f"We're refunding you {_rupees(amount_paise)}.",
        body=(
            f"Hi {_first_name(full_name)}, Pacifyco is refunding you {_rupees(amount_paise)} for a booking.\n"
            f"The reason: {reason}\nWe'll pay it back by UPI or bank transfer, and it will show in your payments."
        ),
        button_label="See your payments",
        button_url=f"{web_url.rstrip('/')}/parent/payments",
    )


def charge_waived(to: str, full_name: str | None, amount_paise: int, reason: str, web_url: str) -> Email:
    """To the parent: an admin waived a charge they owed."""
    return Email(
        to=to,
        subject="Pacifyco has waived a charge",
        heading="You don't need to pay this charge.",
        body=(
            f"Hi {_first_name(full_name)}, Pacifyco has waived a charge of {_rupees(amount_paise)}, so you don't owe "
            f"it any more.\nThe reason: {reason}"
        ),
        button_label="See your payments",
        button_url=f"{web_url.rstrip('/')}/parent/payments",
    )


def extra_pay(to: str, full_name: str | None, amount_paise: int, note: str, web_url: str) -> Email:
    """To the sitter: an admin added pay for a booking."""
    return Email(
        to=to,
        subject="Pacifyco has added to your pay",
        heading=f"We've added {_rupees(amount_paise)} to your pay.",
        body=(
            f"Hi {_first_name(full_name)}, Pacifyco has added {_rupees(amount_paise)} to your pay for a booking.\n"
            f"{note}\nIt's paid with your other earnings."
        ),
        button_label="See your earnings",
        button_url=f"{web_url.rstrip('/')}/sitter/earnings",
    )


# ---------- complaints and grievances (CLAUDE.md 6.12; phase 10, Reuben 2026-11-23) ----------

COMPLAINT_WORDS = {
    "booking": "a booking",
    "payment": "a payment",
    "family": "a family",
    "sitter": "a sitter",
    "review": "a review",
    "suspension": "a decision on their account",
    "data_request": "their data",
    "other": "something else",
}


def complaint_alert(to: str, kind: str, role: str, late: bool, complaint_url: str) -> Email:
    """To admins: a new complaint. No names or details, only where to read it."""
    return Email(
        to=to,
        subject="A new complaint on Pacifyco",
        heading=f"A {role} has raised a complaint.",
        body=(
            f"It's about {COMPLAINT_WORDS.get(kind, 'something else')}"
            + (" and was raised more than 24 hours after it happened." if late else ".")
            + " Please reply within 24 hours and aim to resolve it within 48."
        ),
        button_label="Open the complaint",
        button_url=complaint_url,
    )


def appeal_alert(to: str, role: str, complaint_url: str) -> Email:
    """To admins: an appeal against a suspension or removal."""
    return Email(
        to=to,
        subject="A new appeal on Pacifyco",
        heading=f"A {role} has appealed a decision on their account.",
        body=(
            "An admin who didn't make the decision must review it within 7 working days. "
            "The admin who made it can't handle the appeal."
        ),
        button_label="Open the appeal",
        button_url=complaint_url,
    )


def complaint_message_alert(to: str, complaint_url: str) -> Email:
    """To admins: the person wrote on their complaint."""
    return Email(
        to=to,
        subject="A new message on a complaint",
        heading="Someone has written on their complaint.",
        body="Please read it and reply.",
        button_label="Open the complaint",
        button_url=complaint_url,
    )


def complaint_reply(to: str, full_name: str | None, message: str, complaint_url: str) -> Email:
    """To the person: Pacifyco wrote on their complaint."""
    return Email(
        to=to,
        subject="Pacifyco has replied to your complaint",
        heading="We've replied to your complaint.",
        body=f"Hi {_first_name(full_name)}, here's our reply:\n{message}\nYou can answer in the app.",
        button_label="Read and reply",
        button_url=complaint_url,
    )


def complaint_resolved(to: str, full_name: str | None, resolution: str, complaint_url: str) -> Email:
    """To the person: their complaint is resolved, with what was done."""
    return Email(
        to=to,
        subject="Your Pacifyco complaint is resolved",
        heading="We've resolved your complaint.",
        body=(
            f"Hi {_first_name(full_name)}, here's what we've done:\n{resolution}\n"
            "If you disagree, you can send it to our Grievance Officer from the complaint in the app."
        ),
        button_label="Open the complaint",
        button_url=complaint_url,
    )


def complaint_escalated(to: str, full_name: str | None, overdue: bool, complaint_url: str) -> Email:
    """To the person: their complaint is with the Grievance Officer."""
    why = (
        "We haven't resolved your complaint in time, so it's gone to our Grievance Officer."
        if overdue
        else "Your complaint has gone to our Grievance Officer, as you asked."
    )
    return Email(
        to=to,
        subject="Your complaint is with Pacifyco's Grievance Officer",
        heading="Your complaint is with our Grievance Officer.",
        body=(
            f"Hi {_first_name(full_name)}, {why[0].lower()}{why[1:]} They'll acknowledge it within 24 hours and "
            "send you a written decision, with reasons, within 15 days."
        ),
        button_label="Open the complaint",
        button_url=complaint_url,
    )


def escalation_alert(to: str, count: int, web_url: str) -> Email:
    """To the Grievance Officer: complaints escalated to them."""
    many = count != 1
    return Email(
        to=to,
        subject=f"{count} complaint{'s' if many else ''} escalated to the Grievance Officer",
        heading=f"{count} complaint{'s have' if many else ' has'} been escalated to you.",
        body="Please acknowledge within 24 hours and send a written decision, with reasons, within 15 days.",
        button_label="Open escalated complaints",
        button_url=f"{web_url.rstrip('/')}/admin/complaints?view=escalated",
    )


def officer_decision(to: str, full_name: str | None, decision: str, complaint_url: str) -> Email:
    """To the person: the Grievance Officer's written decision."""
    return Email(
        to=to,
        subject="The Grievance Officer's decision on your complaint",
        heading="Our Grievance Officer has decided your complaint.",
        body=f"Hi {_first_name(full_name)}, here is the decision and the reasons for it:\n{decision}",
        button_label="Open the complaint",
        button_url=complaint_url,
    )


def appeal_decided(
    to: str, full_name: str | None, upheld: bool, reinstated: bool, note: str, complaint_url: str
) -> Email:
    """To the person: their appeal was decided."""
    if upheld and reinstated:
        outcome = "We've upheld your appeal and your account is active again."
    elif upheld:
        outcome = "We've upheld your appeal. We'll let you know as soon as your account is active again."
    else:
        outcome = "We've looked at your appeal carefully, and the decision stands."
    return Email(
        to=to,
        subject="The decision on your Pacifyco appeal",
        heading="We've decided your appeal.",
        body=(
            f"Hi {_first_name(full_name)}, {outcome[0].lower()}{outcome[1:]}\nThe reasons: {note}\n"
            "If you disagree, you can send it to our Grievance Officer from your appeal in the app."
        ),
        button_label="Open Pacifyco",
        button_url=complaint_url,
    )


# ---------- closing their own account (6.13; phase 10, Reuben 2026-11-23) ----------


def account_closed(to: str, full_name: str | None, pay_due_paise: int) -> Email:
    """To the person: they closed their account. A sitter's pay still due is paid as usual."""
    pay = (
        f" The {_rupees(pay_due_paise)} you've earned and haven't been paid yet will still be paid to you as usual."
        if pay_due_paise
        else ""
    )
    return Email(
        to=to,
        subject="Your Pacifyco account is closed",
        heading="Your account is closed.",
        body=(
            f"Hi {_first_name(full_name)}, you've closed your Pacifyco account, so it can't be used any more.{pay}\n"
            "If you'd like it reopened, or your data deleted, write to founders@pacifyco.in."
        ),
        button_label="Contact Pacifyco",
        button_url="mailto:founders@pacifyco.in",
    )


# ---------- gaps found in phase 11 (2026-11-23) ----------


def booking_confirmed_for_sitter(
    to: str, full_name: str | None, family_name: str, starts_at: datetime, booking_id: object, web_url: str
) -> Email:
    """To the sitter: the family has paid, so the booking she accepted is confirmed (6.4)."""
    return Email(
        to=to,
        subject="Your Pacifyco booking is confirmed",
        heading="Your booking is confirmed.",
        body=(
            f"Hi {_first_name(full_name)}, {family_name}'s family has paid, so your booking for {_when(starts_at)} "
            "is confirmed.\nYou can now see the home address and the family's emergency contact on the booking."
        ),
        button_label="See the booking",
        button_url=f"{web_url.rstrip('/')}/sitter/bookings/{booking_id}",
    )


def unpaid_cancelled_for_parent(
    to: str, full_name: str | None, sitter_name: str | None, starts_at: datetime, web_url: str
) -> Email:
    """To the parent: the booking wasn't paid 3 hours before the start, so it was cancelled (6.1)."""
    sitter = _first_name(sitter_name) if sitter_name else "your sitter"
    return Email(
        to=to,
        subject="Your Pacifyco booking was cancelled",
        heading="Your booking was cancelled.",
        body=(
            f"Hi {_first_name(full_name)}, your booking with {sitter} for {_when(starts_at)} wasn't paid 3 hours "
            "before the start, so it has been cancelled. You haven't been charged.\n"
            "You're welcome to book again."
        ),
        button_label="Find a sitter",
        button_url=f"{web_url.rstrip('/')}/parent/sitters",
    )


def unpaid_cancelled_for_sitter(
    to: str, full_name: str | None, family_name: str, starts_at: datetime, web_url: str
) -> Email:
    """To the sitter: the family didn't pay in time, so the booking she accepted is cancelled (6.1)."""
    return Email(
        to=to,
        subject="A booking was cancelled",
        heading="A booking you accepted was cancelled.",
        body=(
            f"Hi {_first_name(full_name)}, {family_name}'s family didn't pay in time, so their booking for "
            f"{_when(starts_at)} is cancelled. That time is free again for other families."
        ),
        button_label="See your bookings",
        button_url=f"{web_url.rstrip('/')}/sitter/bookings",
    )


def unverified_cancelled_for_parent(to: str, full_name: str | None, starts_at: datetime, web_url: str) -> Email:
    """To the parent: a paid booking couldn't go ahead because a child on it wasn't verified by the start."""
    return Email(
        to=to,
        subject="Your Pacifyco booking was cancelled",
        heading="Your booking was cancelled.",
        body=(
            f"Hi {_first_name(full_name)}, a child on your booking for {_when(starts_at)} wasn't verified by the "
            "start, so the booking couldn't go ahead. Pacifyco will refund you in full."
        ),
        button_label="See your payments",
        button_url=f"{web_url.rstrip('/')}/parent/payments",
    )


def psych_retake_allowed(to: str, full_name: str | None, web_url: str) -> Email:
    """To the sitter: an admin has let her take the psychology screening again (7)."""
    return Email(
        to=to,
        subject="You can take the screening again",
        heading="You can take the psychology screening again.",
        body=f"Hi {_first_name(full_name)}, Pacifyco has opened the psychology screening for you to take again.",
        button_label="Take the screening",
        button_url=f"{web_url.rstrip('/')}/sitter/psych-test",
    )
