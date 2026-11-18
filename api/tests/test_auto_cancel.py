# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Pacifyco's own cancellations of unpaid bookings (CLAUDE.md 6.1, 6.4 and 9 "Plans and pricing",
"Bookings"; phase 6 "Frequent job").

- With no payment sent by 3 hours before the start, a `pending_payment` booking is cancelled
  (`cancelled_unpaid`) by the frequent job, or as soon as the parent opens it. One whose UPI reference
  was sent in time waits for an admin (Reuben, 2026-11-18); a rejected payment doesn't keep it.
- Once a booking is confirmed, other `pending_payment` (and paid `awaiting_verification`) bookings with
  her for an overlapping time are cancelled (`cancelled_slot_taken`).
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import Booking
from app.services import bookings, jobs
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_documents import client, parent, row, rows, scalar, storage  # noqa: F401  (fixtures)
from tests.test_jobs import SECRET, bearer
from tests.test_jobs import client as jobs_client
from tests.test_marketplace import at, finished_parent, india_day, make_sitter  # noqa: F401  (fixtures)
from tests.test_payments import booking, get, pay  # noqa: F401  (fixture)
from tests.test_sign_up import auth_for, user  # noqa: F401  (fixture)


def move(db_engine, booking_id, starts_at: datetime, hours: int = 2) -> None:
    """Puts a booking at another time (the API only takes bookings 4+ hours ahead)."""
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE bookings SET starts_at = :s, ends_at = :e WHERE id = :b"),
            {"s": starts_at, "e": starts_at + timedelta(hours=hours), "b": booking_id},
        )


def status(db_engine, booking_id) -> str:
    return scalar(db_engine, "SELECT status FROM bookings WHERE id = :b", b=booking_id)


def cancel_unpaid(db_engine, now: datetime) -> list:
    with Session(db_engine) as db:
        cancelled = bookings.cancel_unpaid(db, now)
        db.commit()
    return [str(item) for item in cancelled]


# ---------- the payment deadline ----------


def test_the_frequent_run_cancels_unpaid_bookings_past_the_deadline(client, db_engine, booking):
    move(db_engine, booking["id"], datetime.now(UTC) + timedelta(hours=2))
    response = jobs_client(db_engine).post("/internal/jobs/frequent", headers=bearer(SECRET))
    assert response.status_code == 200
    assert response.json() == {"run": "frequent", "ran": ["cancel_unpaid_bookings", "cancel_unverified_bookings"]}
    assert status(db_engine, booking["id"]) == "cancelled_unpaid"
    audit = row(
        db_engine,
        "SELECT actor_id, action, before, after FROM audit_log WHERE entity = 'booking' AND entity_id = :b"
        " AND action = 'booking_cancelled'",
        b=booking["id"],
    )
    assert audit["actor_id"] is None  # Pacifyco, not a person
    assert audit["before"] == {"status": "pending_payment"}
    assert audit["after"] == {"status": "cancelled_unpaid", "reason": "not_paid_by_deadline"}


def test_the_deadline_is_exactly_3_hours_before_the_start(client, db_engine, booking):
    starts_at = at(india_day(3), 10)
    move(db_engine, booking["id"], starts_at)
    assert cancel_unpaid(db_engine, starts_at - timedelta(hours=3, seconds=1)) == []
    assert status(db_engine, booking["id"]) == "pending_payment"
    assert cancel_unpaid(db_engine, starts_at - timedelta(hours=3)) == [booking["id"]]
    assert status(db_engine, booking["id"]) == "cancelled_unpaid"


def test_running_again_changes_nothing(client, db_engine, booking):
    starts_at = at(india_day(3), 10)
    move(db_engine, booking["id"], starts_at)
    assert cancel_unpaid(db_engine, starts_at) == [booking["id"]]
    assert cancel_unpaid(db_engine, starts_at + timedelta(hours=1)) == []
    count = "SELECT count(*) FROM audit_log WHERE action = 'booking_cancelled' AND entity_id = :b"
    assert scalar(db_engine, count, b=booking["id"]) == 1


def test_a_reference_sent_in_time_keeps_the_booking_for_an_admin(client, db_engine, booking, finished_parent):
    assert pay(client, finished_parent, booking["id"]).status_code == 201
    starts_at = at(india_day(3), 10)
    move(db_engine, booking["id"], starts_at)
    assert cancel_unpaid(db_engine, starts_at) == []
    assert status(db_engine, booking["id"]) == "pending_payment"


def test_a_rejected_payment_doesnt_keep_the_booking(client, db_engine, booking, finished_parent):
    assert pay(client, finished_parent, booking["id"]).status_code == 201
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE payments SET status = 'rejected', rejection_reason = 'Not received' WHERE booking_id = :b"),
            {"b": booking["id"]},
        )
    starts_at = at(india_day(3), 10)
    move(db_engine, booking["id"], starts_at)
    assert cancel_unpaid(db_engine, starts_at) == [booking["id"]]


@pytest.mark.parametrize("other", ["confirmed", "cancelled_parent"])
def test_only_bookings_waiting_for_payment_are_cancelled(client, db_engine, booking, other):
    starts_at = at(india_day(3), 10)
    move(db_engine, booking["id"], starts_at)
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE bookings SET status = :s WHERE id = :b"), {"s": other, "b": booking["id"]})
    assert cancel_unpaid(db_engine, starts_at) == []
    assert status(db_engine, booking["id"]) == other


def test_opening_the_booking_after_the_deadline_shows_it_cancelled(client, db_engine, booking, finished_parent):
    # Between midnight and 6 am the frequent run doesn't go, so the booking is checked when opened too.
    move(db_engine, booking["id"], datetime.now(UTC) + timedelta(hours=2, minutes=59))
    found = get(client, finished_parent, booking["id"]).json()
    assert found["status"] == "cancelled_unpaid"
    assert found["pay_by_upi"] is None
    response = pay(client, finished_parent, booking["id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_waiting_for_payment"


def test_opening_it_before_the_deadline_changes_nothing(client, db_engine, booking, finished_parent):
    assert get(client, finished_parent, booking["id"]).json()["status"] == "pending_payment"


# ---------- the first confirmed booking wins her time ----------


def test_a_confirmed_booking_cancels_overlapping_unpaid_ones(client, db_engine, finished_parent, free_sitter, child_of):
    sitter = free_sitter("unwind")
    other_sitter = free_sitter("unwind")
    kid = children_of(db_engine, finished_parent["id"])[:1]

    def booked(who_for, hour, hours=2):
        made = book(client, finished_parent, who_for, child_ids=kid, hours=hours)
        assert made.status_code == 201, made.text
        move(db_engine, made.json()["id"], at(india_day(2), hour), hours)
        return made.json()["id"]

    winner = booked(sitter, 10)  # 10 am - 12 pm
    overlapping = booked(sitter, 11)  # 11 am - 1 pm
    inside = booked(sitter, 10, hours=1)  # 10 - 11 am
    touching = booked(sitter, 12)  # 12 - 2 pm: starts as the winner ends
    elsewhere = booked(other_sitter, 10)  # another sitter, same time
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE bookings SET status = 'confirmed' WHERE id = :b"), {"b": winner})

    with Session(db_engine) as db:
        cancelled = bookings.cancel_overlapping(db, db.get(Booking, winner))
        db.commit()
    assert sorted(str(item) for item in cancelled) == sorted([overlapping, inside])
    assert status(db_engine, overlapping) == status(db_engine, inside) == "cancelled_slot_taken"
    assert status(db_engine, touching) == status(db_engine, elsewhere) == "pending_payment"
    assert status(db_engine, winner) == "confirmed"
    audit = row(
        db_engine,
        "SELECT after FROM audit_log WHERE action = 'booking_cancelled' AND entity_id = :b",
        b=overlapping,
    )
    assert audit["after"] == {"status": "cancelled_slot_taken", "taken_by": winner}


def test_the_frequent_job_task_is_listed():
    assert ("cancel_unpaid_bookings", jobs.cancel_unpaid_bookings) in jobs.RUNS["frequent"]
