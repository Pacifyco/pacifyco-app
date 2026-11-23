# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Emails that were missing, found in the phase 11 check (2026-11-23).

- The sitter hears her booking is confirmed once the family's payment is confirmed (only the parent did).
- Bookings the rules cancel (unpaid by the deadline; a child unverified by the start) are emailed, once, by
  the frequent job, however the cancellation happened: the parent, and for an unpaid one the sitter too.
  Automatic cancellations from before these emails existed aren't emailed.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from tests.test_admin_payments import confirm, paid, verify_children  # noqa: F401
from tests.test_auto_cancel import move, status
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_cancellations import to
from tests.test_documents import admin, client, parent, scalar, storage  # noqa: F401
from tests.test_jobs import SECRET, bearer
from tests.test_jobs import client as jobs_client
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_payments import booking, get  # noqa: F401  (fixture)
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import auth_for, user  # noqa: F401  (fixture)
from tests.test_sitter_bookings import signed_in
from tests.test_verification import reviewer  # noqa: F401  (fixture)


def frequent(db_engine, mailbox):
    response = jobs_client(db_engine, mailbox=mailbox).post("/internal/jobs/frequent", headers=bearer(SECRET))
    assert response.status_code == 200, response.text


def test_the_sitter_hears_her_booking_is_confirmed(
    client, db_engine, mailbox, reviewer, booking, finished_parent, paid
):
    sitter = signed_in(db_engine, booking["sitter_id"])
    verify_children(db_engine, finished_parent["id"])
    mailbox.sent.clear()
    assert confirm(client, reviewer, paid).json()["booking_status"] == "confirmed"
    (told,) = to(mailbox, sitter["email"])
    assert told.subject == "Your Pacifyco booking is confirmed"
    assert "Meera's family has paid" in told.body and "home address" in told.body
    assert told.button_url.endswith(f"/sitter/bookings/{booking['id']}")
    assert to(mailbox, finished_parent["email"])[0].heading == "Your booking is confirmed."


def test_an_unpaid_booking_cancelled_by_the_rules_is_emailed_once(client, db_engine, mailbox, booking, finished_parent):
    sitter = signed_in(db_engine, booking["sitter_id"])
    move(db_engine, booking["id"], datetime.now(UTC) + timedelta(hours=2))  # inside the 3-hour deadline, unpaid
    get(client, finished_parent, booking["id"])  # opening it cancels it, before any job run
    assert status(db_engine, booking["id"]) == "cancelled_unpaid"
    mailbox.sent.clear()
    frequent(db_engine, mailbox)
    (parent_told,) = to(mailbox, finished_parent["email"])
    assert parent_told.subject == "Your Pacifyco booking was cancelled"
    assert "wasn't paid 3 hours before the start" in parent_told.body and "haven't been charged" in parent_told.body
    (sitter_told,) = to(mailbox, sitter["email"])
    assert "didn't pay in time" in sitter_told.body and "free again" in sitter_told.body

    mailbox.sent.clear()
    frequent(db_engine, mailbox)  # never twice
    assert to(mailbox, finished_parent["email"]) == [] and to(mailbox, sitter["email"]) == []


def test_older_automatic_cancellations_arent_emailed(client, db_engine, mailbox, booking, finished_parent):
    move(db_engine, booking["id"], datetime.now(UTC) + timedelta(hours=2))
    get(client, finished_parent, booking["id"])
    with db_engine.begin() as conn:  # as if it had been cancelled before these emails existed
        conn.execute(
            text(
                "UPDATE audit_log SET created_at = now() - interval '2 days'"
                " WHERE entity_id = :b AND action = 'booking_cancelled'"
            ),
            {"b": booking["id"]},
        )
    mailbox.sent.clear()
    frequent(db_engine, mailbox)
    assert to(mailbox, finished_parent["email"]) == []


def test_a_paid_booking_cancelled_for_an_unverified_child_is_emailed(
    client, db_engine, mailbox, booking, finished_parent
):
    with db_engine.begin() as conn:  # an older paid booking still waiting for a child's verification (6.4)
        conn.execute(text("UPDATE bookings SET status = 'awaiting_verification' WHERE id = :b"), {"b": booking["id"]})
    move(db_engine, booking["id"], datetime.now(UTC) - timedelta(minutes=5))  # it has started
    mailbox.sent.clear()
    frequent(db_engine, mailbox)
    assert status(db_engine, booking["id"]) == "cancelled_unverified"
    (told,) = to(mailbox, finished_parent["email"])
    assert "wasn't verified by the start" in told.body and "refund you in full" in told.body
    sitter_email = scalar(db_engine, "SELECT email FROM profiles WHERE id = :s", s=booking["sitter_id"])
    assert to(mailbox, sitter_email) == []  # that booking never held her time
