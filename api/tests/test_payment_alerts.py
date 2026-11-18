# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Admins are emailed about booking payments still unchecked as the booking nears its start (Reuben,
2026-11-19: "about an hour before"), once for each payment, by the frequent job."""

from datetime import UTC, datetime, timedelta

from tests.conftest import Mailbox
from tests.test_admin_payments import confirm, paid, payment_id, verify_children  # noqa: F401  (fixture)
from tests.test_auto_cancel import move
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_documents import admin, client, parent, row, rows, scalar, storage  # noqa: F401  (fixtures)
from tests.test_jobs import SECRET, bearer
from tests.test_jobs import client as jobs_client
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_payments import booking, pay  # noqa: F401  (fixture)
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import auth_for, user  # noqa: F401  (fixture)
from tests.test_verification import reviewer  # noqa: F401  (fixture)

ADMINS = "ops@example.com, founders@example.com"


def run(db_engine, mailbox, admins=ADMINS):
    response = jobs_client(db_engine, mailbox=mailbox, admin_alert_emails=admins).post(
        "/internal/jobs/frequent", headers=bearer(SECRET)
    )
    assert response.status_code == 200, response.text


def alerts(mailbox):
    return [email for email in mailbox.sent if email.button_label == "Check payments"]


def test_an_unchecked_payment_near_the_start_is_alerted_once(db_engine, booking, paid):
    move(db_engine, booking["id"], datetime.now(UTC) + timedelta(minutes=70))
    mailbox = Mailbox()
    run(db_engine, mailbox)
    sent = alerts(mailbox)
    assert sorted(email.to for email in sent) == ["founders@example.com", "ops@example.com"]
    email = sent[0]
    assert email.heading == "1 payment still to check."
    assert email.button_url == "https://staging.example/admin/payments"
    assert "123456789012" not in email.body  # no reference, names or amounts in the email
    assert (
        scalar(
            db_engine,
            "SELECT count(*) FROM audit_log WHERE action = 'unchecked_payment_alerted' AND entity_id = :p",
            p=paid,
        )
        == 1
    )

    again = Mailbox()  # the next run doesn't send it again
    run(db_engine, again)
    assert alerts(again) == []


def test_not_yet_when_the_start_is_further_off(db_engine, booking, paid):
    move(db_engine, booking["id"], datetime.now(UTC) + timedelta(hours=2))
    mailbox = Mailbox()
    run(db_engine, mailbox)
    assert alerts(mailbox) == []


def test_a_checked_payment_isnt_alerted(client, reviewer, db_engine, booking, finished_parent, paid):
    verify_children(db_engine, finished_parent["id"])
    assert confirm(client, reviewer, paid).status_code == 200
    move(db_engine, booking["id"], datetime.now(UTC) + timedelta(minutes=30))
    mailbox = Mailbox()
    run(db_engine, mailbox)
    assert alerts(mailbox) == []


def test_with_no_admin_addresses_it_waits_until_one_is_set(db_engine, booking, paid):
    move(db_engine, booking["id"], datetime.now(UTC) + timedelta(minutes=45))
    mailbox = Mailbox()
    run(db_engine, mailbox, admins="")
    assert alerts(mailbox) == []
    run(db_engine, mailbox)
    assert len(alerts(mailbox)) == 2
