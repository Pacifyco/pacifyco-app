# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Booking requests: the sitter accepts before the parent pays (CLAUDE.md 6.4; Reuben, 2026-11-19).

- A new booking is a request. The sitter sees it only once every child on it is verified.
- She has 5 hours from when she can see it to answer; it lapses then, or 4 hours before the start if
  that's sooner. Declining has no penalty; the parent is told either way.
- Accepting holds her time while the parent pays, and declines other requests for an overlapping time.
- On a request she sees everything but the home address and the emergency contact.
- Bookings start at least 6 hours from now.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from tests.test_admin_payments import another_family, confirm, payment_id, verify_children  # noqa: F401
from tests.test_auto_cancel import move, status
from tests.test_bookings import book, child_of, children_of, free_sitter, options  # noqa: F401  (fixtures)
from tests.test_documents import admin, client, parent, row, rows, scalar, storage  # noqa: F401  (fixtures)
from tests.test_jobs import SECRET, bearer
from tests.test_jobs import client as jobs_client
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_payments import get, pay  # noqa: F401
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import auth_for, user  # noqa: F401  (fixture)
from tests.test_verification import review, reviewer  # noqa: F401  (fixture)


def requests_of(client, sitter):
    response = client.get("/sitter/requests", headers=auth_for(sitter))
    assert response.status_code == 200, response.text
    return response.json()


def answer(client, sitter, booking_id, how):
    return client.post(f"/sitter/bookings/{booking_id}/{how}", headers=auth_for(sitter))


def request(client, db_engine, who, sitter, verified=True, **kwargs):
    """A request from this parent to this sitter (every child verified unless told otherwise)."""
    if verified:
        verify_children(db_engine, who["id"])
    kids = children_of(db_engine, who["id"])[:1]
    response = book(client, who, sitter, child_ids=kids, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()


def to(mailbox, address):
    return [email for email in mailbox.sent if email.to == address]


def at_least(moment: str, expected: datetime) -> None:
    assert abs(datetime.fromisoformat(moment) - expected) < timedelta(minutes=1)


# ---------- seeing a request ----------


def test_a_request_with_every_child_verified_reaches_the_sitter(
    client, db_engine, mailbox, finished_parent, free_sitter
):
    sitter = free_sitter("unwind")
    made = request(client, db_engine, finished_parent, sitter)
    assert made["status"] == "requested" and made["seen_by_sitter"] is True
    assert made["pay_by_upi"] is None  # nothing to pay until she accepts
    starts = datetime.fromisoformat(made["starts_at"])
    expected = min(datetime.now(UTC) + timedelta(hours=5), starts - timedelta(hours=4))
    at_least(made["answer_by"], expected)

    (item,) = requests_of(client, sitter)
    assert item["id"] == made["id"] and item["status"] == "requested"
    at_least(item["answer_by"], expected)
    email = to(mailbox, sitter["email"])[-1]
    assert email.heading == "You have a new booking request."
    assert email.button_url.endswith(f"/sitter/bookings/{made['id']}")


def test_she_sees_everything_but_the_address_and_contact(client, db_engine, finished_parent, free_sitter):
    sitter = free_sitter("unwind")
    made = request(client, db_engine, finished_parent, sitter)
    found = client.get(f"/sitter/bookings/{made['id']}", headers=auth_for(sitter)).json()
    assert found["address"] is None and found["emergency_contact"] is None
    assert found["pin_code"] == "560034"  # the area
    assert found["children_details"] and found["pay_paise"] == 2 * 30_000
    assert "price" not in str(found).lower()


def test_unverified_children_keep_it_from_her_until_approved(
    client, reviewer, db_engine, mailbox, finished_parent, free_sitter
):
    sitter = free_sitter("unwind")
    made = request(client, db_engine, finished_parent, sitter, verified=False)
    assert made["seen_by_sitter"] is False
    assert requests_of(client, sitter) == []
    assert client.get(f"/sitter/bookings/{made['id']}", headers=auth_for(sitter)).status_code == 404
    assert answer(client, sitter, made["id"], "accept").status_code == 404
    assert to(mailbox, sitter["email"]) == []

    child = children_of(db_engine, finished_parent["id"])[0]
    assert review(client, reviewer, f"/admin/children/{child}/decision").status_code == 200
    (item,) = requests_of(client, sitter)
    assert item["id"] == made["id"]
    at_least(item["answer_by"], datetime.now(UTC) + timedelta(hours=5))  # her 5 hours start now
    assert to(mailbox, sitter["email"])[-1].heading == "You have a new booking request."


# ---------- accepting ----------


def test_accepting_holds_her_time_and_the_parent_pays(
    client, db_engine, mailbox, finished_parent, free_sitter, another_family
):
    sitter = free_sitter("unwind")
    made = request(client, db_engine, finished_parent, sitter)
    other, kid = another_family
    verify_children(db_engine, other["id"])
    theirs = book(client, other, sitter, child_ids=[kid]).json()  # same time: requests don't hold it
    assert theirs["status"] == "requested"

    response = answer(client, sitter, made["id"], "accept")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "pending_payment"
    assert response.json()["address"] is None  # not until it's paid and confirmed

    shown = get(client, finished_parent, made["id"]).json()
    assert shown["status"] == "pending_payment"
    email = to(mailbox, finished_parent["email"])[-1]
    assert "has accepted your booking" in email.heading and email.button_label == "Pay for your booking"

    # The other family's request for that time is declined, and they're told.
    assert status(db_engine, theirs["id"]) == "request_declined"
    assert "can't take your booking" in to(mailbox, other["email"])[-1].heading
    # Her time is held: nobody can book it now.
    start = datetime.fromisoformat(made["starts_at"])
    times = options(client, other, sitter)["times"]
    assert not any(
        datetime.fromisoformat(t["starts_at"]) <= start < datetime.fromisoformat(t["ends_at"]) for t in times
    )
    assert book(client, other, sitter, child_ids=[kid]).status_code == 409

    audit = row(
        db_engine,
        "SELECT actor_id, after FROM audit_log WHERE action = 'request_accepted' AND entity_id = :b",
        b=made["id"],
    )
    assert str(audit["actor_id"]) == str(sitter["id"]) and audit["after"] == {"status": "pending_payment"}


def test_the_address_shows_once_paid_and_confirmed(client, reviewer, db_engine, finished_parent, free_sitter):
    sitter = free_sitter("unwind")
    made = request(client, db_engine, finished_parent, sitter)
    assert answer(client, sitter, made["id"], "accept").status_code == 200
    assert pay(client, finished_parent, made["id"]).status_code == 201
    assert confirm(client, reviewer, payment_id(db_engine, made["id"])).json()["booking_status"] == "confirmed"
    found = client.get(f"/sitter/bookings/{made['id']}", headers=auth_for(sitter)).json()
    assert found["address"] and found["emergency_contact"]


def test_a_request_is_answered_once_and_only_by_her(client, db_engine, finished_parent, free_sitter):
    sitter = free_sitter("unwind")
    made = request(client, db_engine, finished_parent, sitter)
    assert answer(client, free_sitter("unwind"), made["id"], "accept").status_code == 404
    assert client.post(f"/sitter/bookings/{made['id']}/accept", headers=auth_for(finished_parent)).status_code == 403
    assert answer(client, sitter, made["id"], "decline").status_code == 200
    again = answer(client, sitter, made["id"], "accept")
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_answered"


# ---------- declining and lapsing ----------


def test_declining_tells_the_parent_and_frees_nothing_to_pay(client, db_engine, mailbox, finished_parent, free_sitter):
    sitter = free_sitter("unwind")
    made = request(client, db_engine, finished_parent, sitter)
    response = answer(client, sitter, made["id"], "decline")
    assert response.status_code == 200 and response.json()["status"] == "request_declined"
    email = to(mailbox, finished_parent["email"])[-1]
    assert "can't take your booking" in email.heading and "haven't been charged" in email.body
    assert pay(client, finished_parent, made["id"]).status_code == 409
    assert requests_of(client, sitter) == []
    no_strike = scalar(
        db_engine, "SELECT count(*) FROM audit_log WHERE action LIKE '%strike%' AND entity_id = :s", s=str(sitter["id"])
    )
    assert no_strike == 0


def test_unanswered_for_5_hours_it_lapses(client, db_engine, mailbox, finished_parent, free_sitter):
    sitter = free_sitter("unwind")
    made = request(client, db_engine, finished_parent, sitter)
    with db_engine.begin() as conn:  # she could see it 5 hours ago
        conn.execute(
            text("UPDATE bookings SET request_visible_at = :t WHERE id = :b"),
            {"t": datetime.now(UTC) - timedelta(hours=5, minutes=1), "b": made["id"]},
        )
    assert requests_of(client, sitter) == []  # opening her requests lapses it
    assert status(db_engine, made["id"]) == "request_lapsed"
    email = to(mailbox, finished_parent["email"])[-1]
    assert "didn't answer your request in time" in email.heading
    late = answer(client, sitter, made["id"], "accept")
    assert late.status_code == 409 and late.json()["error"]["code"] == "request_lapsed"


def test_it_lapses_4_hours_before_the_start_even_unseen(client, db_engine, mailbox, finished_parent, free_sitter):
    sitter = free_sitter("unwind")
    made = request(client, db_engine, finished_parent, sitter, verified=False)
    move(db_engine, made["id"], datetime.now(UTC) + timedelta(hours=3, minutes=59))
    run = jobs_client(db_engine, mailbox=mailbox).post("/internal/jobs/frequent", headers=bearer(SECRET))
    assert run.status_code == 200 and "lapse_requests" in run.json()["ran"]
    assert status(db_engine, made["id"]) == "request_lapsed"
    assert "didn't answer your request in time" in to(mailbox, finished_parent["email"])[-1].heading
    shown = get(client, finished_parent, made["id"]).json()
    assert shown["status"] == "request_lapsed" and shown["pay_by_upi"] is None


def test_the_parent_sees_a_lapse_when_they_open_it(client, db_engine, finished_parent, free_sitter):
    sitter = free_sitter("unwind")
    made = request(client, db_engine, finished_parent, sitter)
    move(db_engine, made["id"], datetime.now(UTC) + timedelta(hours=3))
    assert get(client, finished_parent, made["id"]).json()["status"] == "request_lapsed"


# ---------- how soon ----------


def test_bookings_start_at_least_6_hours_ahead(client, db_engine, finished_parent, free_sitter):
    sitter = free_sitter("unwind")
    times = options(client, finished_parent, sitter)["times"]
    earliest = min(datetime.fromisoformat(t["starts_at"]) for t in times)
    assert earliest >= datetime.now(UTC) + timedelta(hours=6)
    # 5 hours ahead, on the hour in India time (India is +05:30)
    soon = (datetime.now(UTC) + timedelta(hours=5, minutes=30)).replace(minute=30, second=0, microsecond=0)
    if soon < datetime.now(UTC) + timedelta(hours=5):
        soon += timedelta(hours=1)
    kids = [str(kid) for kid in children_of(db_engine, finished_parent["id"])[:1]]
    response = client.post(
        "/parent/bookings",
        json={
            "sitter_id": str(sitter["id"]),
            "starts_at": soon.isoformat(),
            "hours": 1,
            "child_ids": kids,
            "cameras_on": False,
        },
        headers=auth_for(finished_parent),
    )
    assert response.status_code == 422 and response.json()["error"]["code"] == "too_soon"
