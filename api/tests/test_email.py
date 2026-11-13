"""Approval emails (brought forward from phase 11, Reuben 2026-11-13): design.md 2's layout, escaped
content, and never failing the request when Resend is down or not set up."""

import httpx2 as httpx

from app.services import email as email_service
from app.settings import Settings

EMAIL = email_service.child_verified("asha@example.com", "Asha K", "Diya <b>", True, "https://pacifyco.in")


def test_the_email_has_one_button_and_the_sign_off():
    page = email_service.render_html(EMAIL)
    assert page.count("<a ") == 1
    assert "https://pacifyco.in/parent/sitters" in page
    assert "Warmly, the Pacify team" in page
    assert "max-width:600px" in page
    assert "<b>" not in page  # names are escaped


def test_without_a_resend_key_nothing_is_sent(monkeypatch):
    calls = []
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: calls.append(args))
    email_service.ResendEmail(Settings(_env_file=None, resend_api_key="", email_from="")).send(EMAIL)
    assert calls == []


def test_a_resend_failure_doesnt_raise(monkeypatch):
    def fail(*args, **kwargs):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", fail)
    email_service.ResendEmail(
        Settings(_env_file=None, resend_api_key="re_test", email_from="Pacify <hello@pacifyco.in>")
    ).send(EMAIL)
