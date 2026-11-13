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
from typing import Annotated, Protocol

import httpx2 as httpx
from fastapi import Depends

from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)

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
