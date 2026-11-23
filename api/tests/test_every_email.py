"""Every email the API can send, built and checked against design.md and CLAUDE.md (phase 11).

Each public function in `app/services/email.py` that returns an `Email` is called with made-up values (once
with a name, once without), so a new email is covered as soon as it's written:

- design.md: 600px, one button, signed "Warmly, the Pacifyco team"; never "Book now".
- CLAUDE.md 1 and 7: the brand is "Pacifyco", never "Pacify"; no claim of a check we don't do (no interview,
  background or address check, no "Pacify Plus") and nothing from dropped features (hour packs).
- Times in India time, money in rupees, no placeholder or "None" left in the words.
- Admin alerts carry no contact details (phone numbers, email addresses): only where to look. Some name the
  sitter they're about (a low-rating flag, a removal), so an admin knows whose it is.
"""

import inspect
import re
from datetime import UTC, datetime

import pytest

from app.services import email as email_module
from app.services.email import Email, render_html, render_text

WEB = "https://pacifyco.example"
NAME = "Meera Rao"
STARTS = datetime(2030, 1, 7, 3, 30, tzinfo=UTC)  # 9:00 am in India
ENDS = datetime(2030, 1, 7, 5, 30, tzinfo=UTC)  # 11:00 am in India

# Values by parameter name. Anything personal is distinctive, so a leak into an admin alert is easy to spot.
VALUES = {
    "to": "person@example.com",
    "full_name": NAME,
    "sitter_name": "Lakshmi Nair",
    "family_name": "Rao",
    "child_name": "Asha",
    "referee": "Anita Desai",
    "web_url": WEB,
    "area_url": f"{WEB}/parent",
    "complaint_url": f"{WEB}/parent/help/c1",
    "button_url": f"{WEB}/parent/bookings/b1",
    "button_label": "Open the booking",
    "heading": "The report is confirmed.",
    "body": "We've confirmed what you reported.",
    "starts_at": STARTS,
    "ends_at": ENDS,
    "answer_by": STARTS,
    "pay_by": STARTS,
    "earliest_due": STARTS,
    "earliest_start": STARTS,
    "blocked_until": ENDS,
    "amount_paise": 139_800,
    "pay_due_paise": 60_000,
    "count": 2,
    "hours": 2,
    "average": "3.2",
    "booking_id": "b1",
    "payment_id": "m1",
    "sitter_id": "s1",
    "reason": "The certificate is blurry.",
    "note": "Stayed for a storm.",
    "message": "We're looking into it.",
    "resolution": "We refunded the second charge.",
    "decision": "Refunded in full, because the charge was a mistake.",
    "where": "Cubbon Park",
    "topic_words": "Running late",
    "step": "identity_documents",
    "which": "check-in",
    "method": "upi",
    "kind": "payment",
    "role": "parent",
    "by": "parent",
}
BOOLS = {"accepted", "family_verified", "lapsed", "late", "overdue", "paid", "refunded", "reinstated", "suspended",
         "upheld", "verified"}  # fmt: skip
# Emailed to ADMIN_ALERT_EMAILS or the Grievance Officer, never to the person.
ADMIN_ALERTS = {name for name in dir(email_module) if name.endswith("_alert")}
NOT_EMAILS = {"render_html", "render_text", "get_email"}
CONTACT = ["person@example.com", "+91", "@example"]  # never in an admin alert
NOT_CLAIMED = [
    r"\binterview",
    r"background check",
    r"address (check|verif)",
    r"pacify plus",
    r"\bhour pack",
    r"\bpacks?\b",
    r"book now",
    r"\bpacify\b(?!co)",
]


def builders():
    for name, function in inspect.getmembers(email_module, inspect.isfunction):
        if function.__module__ == email_module.__name__ and not name.startswith("_") and name not in NOT_EMAILS:
            yield name, function


def build(function, flip: bool = False, **overrides) -> Email:
    args = {}
    for parameter in inspect.signature(function).parameters.values():
        if parameter.name in overrides:
            args[parameter.name] = overrides[parameter.name]
        elif parameter.name in BOOLS:
            args[parameter.name] = flip
        elif parameter.name in VALUES:
            args[parameter.name] = VALUES[parameter.name]
        elif parameter.default is not inspect.Parameter.empty:
            continue
        else:
            raise AssertionError(f"{function.__name__}: no test value for '{parameter.name}'; add one to VALUES")
    return function(**args)


ALL = sorted(name for name, _ in builders())


def test_every_email_is_covered():
    assert len(ALL) > 60  # the sweep found the emails, not an empty list


@pytest.mark.parametrize("name", ALL)
@pytest.mark.parametrize("flip", [False, True], ids=["no", "yes"])
def test_each_email_follows_the_rules(name, flip):
    function = getattr(email_module, name)
    sent = build(function, flip=flip)
    assert isinstance(sent, Email)
    words = " ".join([sent.subject, sent.heading, sent.body, sent.button_label])

    assert sent.subject.strip() and sent.heading.strip() and sent.body.strip() and sent.button_label.strip()
    assert sent.button_url.startswith((WEB, "mailto:founders@pacifyco.in")), sent.button_url
    html = render_html(sent)
    assert 'width="600"' in html and "max-width:600px" in html
    assert html.count("<a ") == 1, "one button, and no other links"
    assert html.rstrip().endswith("</html>") and "Warmly, the Pacifyco team" in html
    assert render_text(sent).rstrip().endswith("Warmly, the Pacifyco team")

    for pattern in NOT_CLAIMED:
        assert not re.search(pattern, words, re.IGNORECASE), f"{name}: '{pattern}' in {words!r}"
    assert "None" not in words and "{" not in words and "}" not in words, words
    assert "3:30" not in words and "5:30 am" not in words, "times are shown in India time, never UTC"
    assert "139800" not in words and "60000" not in words, "money is shown in rupees"
    assert "₹1,398.00" not in words

    if name in ADMIN_ALERTS:
        for contact in CONTACT:
            assert contact not in words, f"{name}: admin alerts carry no contact details ({contact})"


@pytest.mark.parametrize(
    "name", [name for name in ALL if "full_name" in inspect.signature(getattr(email_module, name)).parameters]
)
def test_people_are_greeted_by_first_name_or_there(name):
    function = getattr(email_module, name)
    named = build(function)
    unnamed = build(function, full_name=None)
    assert "Rao" not in named.body.split("\n")[0] or "Meera" in named.body, "first names only"
    if "Meera" in named.body:
        assert "there" in unnamed.body or "Hi," not in unnamed.body
        assert "None" not in unnamed.body
