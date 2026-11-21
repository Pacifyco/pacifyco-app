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


def issue_alert(to: str, topic_words: str, by: str, web_url: str) -> Email:
    """To admins: a non-emergency issue on a booking (6.9)."""
    return Email(
        to=to,
        subject=f"An issue on a Pacifyco booking: {topic_words.lower()}",
        heading=f"A {by} has raised an issue.",
        body=f"{topic_words}. Please get in touch with them, then mark it replied or resolved.",
        button_label="Open the issues",
        button_url=f"{web_url.rstrip('/')}/admin/issues",
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
