# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Booking a sitter (CLAUDE.md 6.1, 6.4, 9 "Plans and pricing" and "Bookings"; phase 6 "Book this sitter").

Whole hours, at least 4 hours from now, inside her free times, by the plan's latest end; Pause one child
only; bath time only on Unwind and Recharge; the camera declaration; children 18 months and over and the
parent's own; `pending_payment` until paid; only confirmed bookings take her time away."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import text

from app.services import bookings
from tests.test_documents import client, parent, row, rows, scalar, storage  # noqa: F401  (fixtures)
from tests.test_marketplace import at, finished_parent, india_day, make_sitter, set_week  # noqa: F401
from tests.test_sign_up import auth_for, user  # noqa: F401  (fixture)
from tests.test_verification import upload

ALL_DAY = [(weekday, 0, 24) for weekday in range(7)]


@pytest.fixture
def child_of(client, db_engine, storage):
    """Adds a child with their birth certificate sent, so the parent's profile stays finished."""

    def add(who, name="Rohan", born=date(2022, 6, 1)) -> uuid.UUID:
        child_id = uuid.uuid4()
        with db_engine.begin() as conn:
            conn.execute(
                text("INSERT INTO children (id, parent_id, name, date_of_birth) VALUES (:id, :p, :name, :born)"),
                {"id": child_id, "p": who["id"], "name": name, "born": born},
            )
        upload(client, storage, who, "birth_certificate", child_id)
        return child_id

    return add


def children_of(db_engine, parent_id) -> list[str]:
    return [
        str(item["id"])
        for item in rows(db_engine, "SELECT id FROM children WHERE parent_id = :p ORDER BY name", p=parent_id)
    ]


def book(client, who, sitter, **fields):
    body = {
        "sitter_id": str(sitter["id"]),
        "starts_at": at(india_day(2), 10).isoformat(),
        "hours": 2,
        "child_ids": fields.pop("child_ids"),
        "cameras_on": False,
        **fields,
    }
    return client.post("/parent/bookings", json=body, headers=auth_for(who))


@pytest.fixture
def free_sitter(client, make_sitter):
    """A live sitter of the chosen level, free all day, every day."""

    def make(level="unwind", week=ALL_DAY):
        sitter = make_sitter(level=level)
        assert set_week(client, sitter, *week).status_code == 200
        return sitter

    return make


def options(client, who, sitter):
    response = client.get(f"/parent/sitters/{sitter['id']}/booking-options", headers=auth_for(who))
    assert response.status_code == 200, response.text
    return response.json()


# ---------- what the booking page offers ----------


def test_options_start_4_hours_from_now_and_end_by_the_plans_latest_end(client, finished_parent, free_sitter):
    sitter = free_sitter("pause")
    found = options(client, finished_parent, sitter)
    assert found["price"] == {"per_hour_paise": 49_900, "extra_child_paise": 0, "one_child_only": True}
    assert found["bath_time_allowed"] is False
    assert found["first_booking"] is True
    times = [(datetime.fromisoformat(t["starts_at"]), datetime.fromisoformat(t["ends_at"])) for t in found["times"]]
    earliest = bookings.earliest_start(datetime.now(UTC))
    assert times and all(start >= earliest - timedelta(minutes=1) for start, _ in times)
    for start, end in times:
        local_start, local_end = start.astimezone(bookings.INDIA), end.astimezone(bookings.INDIA)
        assert local_start.date() == local_end.date()  # split at midnight
        assert local_end.hour <= 18  # Pause ends by 6 pm
        assert local_start.minute == local_end.minute == 0  # whole hours in India time
    # 14 days ahead at most.
    assert max(start for start, _ in times).astimezone(bookings.INDIA).date() <= india_day(13)
    assert "plan" not in found and "rate" not in str(found.keys())


def test_unwind_ends_by_10_pm_and_recharge_by_midnight(client, finished_parent, free_sitter):
    for level, latest in (("unwind", 22), ("recharge", 0)):
        found = options(client, finished_parent, free_sitter(level))
        ends = {datetime.fromisoformat(t["ends_at"]).astimezone(bookings.INDIA).hour for t in found["times"][1:]}
        assert ends == {latest}  # Unwind's 10:30 pm, in whole hours, is 10 pm
        assert found["bath_time_allowed"] is True


def test_options_are_only_for_live_sitters_and_finished_parents(client, parent, finished_parent, make_sitter):
    hidden = make_sitter(live=False)
    response = client.get(f"/parent/sitters/{hidden['id']}/booking-options", headers=auth_for(finished_parent))
    assert response.status_code == 404


# ---------- making a booking ----------


def test_a_booking_waits_for_payment_at_the_plans_price(client, db_engine, finished_parent, free_sitter, child_of):
    sitter = free_sitter("unwind")
    child_of(finished_parent)
    kids = children_of(db_engine, finished_parent["id"])
    response = book(
        client,
        finished_parent,
        sitter,
        hours=3,
        child_ids=kids,
        bath_time=True,
        cameras_on=True,
        camera_locations="  Living room  ",
    )
    assert response.status_code == 201, response.text
    made = response.json()
    assert made["price_paise"] == 84_900 * 3  # Unwind, 2 children: ₹849 an hour
    assert made["status"] == "pending_payment"
    assert made["hours"] == 3
    assert sorted(made["children"]) == ["Asha", "Rohan"]
    assert made["bath_time"] is True
    assert made["camera_locations"] == "Living room"
    starts_at = datetime.fromisoformat(made["starts_at"])
    assert starts_at == at(india_day(2), 10)
    assert datetime.fromisoformat(made["ends_at"]) == at(india_day(2), 13)
    assert datetime.fromisoformat(made["pay_by"]) == at(india_day(2), 7)  # 3 hours before
    assert "plan" not in made and not any("rate" in key or "pay_paise" in key for key in made)

    saved = row(db_engine, "SELECT plan, units, children_count, status FROM bookings WHERE id = :id", id=made["id"])
    assert dict(saved) == {"plan": "unwind", "units": 3, "children_count": 2, "status": "pending_payment"}
    assert scalar(db_engine, "SELECT count(*) FROM booking_children WHERE booking_id = :id", id=made["id"]) == 2
    audit_row = row(db_engine, "SELECT actor_id, action FROM audit_log WHERE entity_id = :id", id=made["id"])
    assert audit_row["action"] == "booking_created" and audit_row["actor_id"] == finished_parent["id"]

    # Only the parent who made it can see it.
    assert client.get(f"/parent/bookings/{made['id']}", headers=auth_for(finished_parent)).json() == made
    other = {"id": uuid.uuid4(), "email": f"{uuid.uuid4()}@example.com"}
    from tests.test_documents import cleanup_documents
    from tests.test_sign_up import PARENT

    try:
        assert client.post("/me/profile", json=PARENT, headers=auth_for(other)).status_code == 201
        assert client.get(f"/parent/bookings/{made['id']}", headers=auth_for(other)).status_code == 404
    finally:
        cleanup_documents(db_engine, other["id"])


def test_recharge_costs_the_same_for_any_number(client, db_engine, finished_parent, free_sitter, child_of):
    sitter = free_sitter("recharge")
    child_of(finished_parent)
    response = book(client, finished_parent, sitter, hours=3, child_ids=children_of(db_engine, finished_parent["id"]))
    assert response.json()["price_paise"] == 269_700  # ₹2,697, the example in CLAUDE.md


def test_pause_takes_one_child_and_no_bath_time(client, db_engine, finished_parent, free_sitter, child_of):
    sitter = free_sitter("pause")
    child_of(finished_parent)
    kids = children_of(db_engine, finished_parent["id"])
    response = book(client, finished_parent, sitter, child_ids=kids)
    assert response.status_code == 422 and response.json()["error"]["code"] == "one_child_only"
    response = book(client, finished_parent, sitter, child_ids=kids[:1], bath_time=True)
    assert response.status_code == 422 and response.json()["error"]["code"] == "no_bath_time"
    assert book(client, finished_parent, sitter, child_ids=kids[:1]).status_code == 201


@pytest.mark.parametrize(
    ("level", "start_hour", "hours", "code"),
    [
        ("pause", 16, 3, "past_latest_end"),  # 7 pm, after Pause's 6 pm
        ("unwind", 21, 2, "past_latest_end"),  # 11 pm, after Unwind's 10:30 pm
        ("recharge", 22, 3, "past_latest_end"),  # 1 am, past midnight
    ],
)
def test_bookings_end_by_the_plans_latest_end(
    client, db_engine, finished_parent, free_sitter, level, start_hour, hours, code
):
    sitter = free_sitter(level)
    kids = children_of(db_engine, finished_parent["id"])
    starts_at = at(india_day(2), start_hour).isoformat()
    response = book(client, finished_parent, sitter, child_ids=kids, starts_at=starts_at, hours=hours)
    assert response.status_code == 422 and response.json()["error"]["code"] == code


def test_bookings_start_at_least_4_hours_from_now(client, db_engine, finished_parent, free_sitter, child_of):
    sitter = free_sitter("recharge")
    kids = children_of(db_engine, finished_parent["id"])
    earliest = bookings.earliest_start(datetime.now(UTC))
    too_soon = book(
        client, finished_parent, sitter, child_ids=kids, starts_at=(earliest - timedelta(hours=1)).isoformat(), hours=1
    )
    assert too_soon.status_code == 422 and too_soon.json()["error"]["code"] == "too_soon"
    if earliest.astimezone(bookings.INDIA).hour < 23:  # the earliest hour itself is fine (unless it's past her day)
        assert (
            book(client, finished_parent, sitter, child_ids=kids, starts_at=earliest.isoformat(), hours=1).status_code
            == 201
        )


def test_bookings_fit_inside_her_free_times(client, db_engine, finished_parent, free_sitter, child_of):
    sitter = free_sitter("recharge", week=[(weekday, 9, 13) for weekday in range(7)])
    kids = children_of(db_engine, finished_parent["id"])
    for start_hour, hours in ((8, 2), (12, 2), (14, 1)):
        response = book(
            client,
            finished_parent,
            sitter,
            child_ids=kids,
            starts_at=at(india_day(2), start_hour).isoformat(),
            hours=hours,
        )
        assert response.status_code == 409 and response.json()["error"]["code"] == "not_free"
    response = book(client, finished_parent, sitter, child_ids=kids, starts_at=at(india_day(2), 9).isoformat(), hours=4)
    assert response.status_code == 201
    # Not past the 14 days parents can book ahead.
    late = at(india_day(15), 10).isoformat()
    response = book(client, finished_parent, sitter, child_ids=kids, starts_at=late, hours=1)
    assert response.status_code == 409


@pytest.mark.parametrize(
    ("starts_at", "hours"),
    [
        (lambda: at(india_day(2), 10) + timedelta(minutes=30), 1),
        (lambda: at(india_day(2), 10), 1.5),
        (lambda: at(india_day(2), 10), 0),
    ],
)
def test_whole_hours_only(client, db_engine, finished_parent, free_sitter, starts_at, hours):
    sitter = free_sitter("recharge")
    kids = children_of(db_engine, finished_parent["id"])
    response = book(client, finished_parent, sitter, child_ids=kids, starts_at=starts_at().isoformat(), hours=hours)
    assert response.status_code == 422
    assert response.json()["error"]["code"] in ("whole_hours_only", "validation_error")


def test_cameras_on_needs_where_they_are(client, db_engine, finished_parent, free_sitter, child_of):
    sitter = free_sitter()
    kids = children_of(db_engine, finished_parent["id"])
    response = book(client, finished_parent, sitter, child_ids=kids, cameras_on=True, camera_locations="  ")
    assert response.status_code == 422 and response.json()["error"]["code"] == "camera_locations_needed"
    missing = client.post(
        "/parent/bookings",
        json={
            "sitter_id": str(sitter["id"]),
            "starts_at": at(india_day(2), 10).isoformat(),
            "hours": 1,
            "child_ids": kids,
        },
        headers=auth_for(finished_parent),
    )
    assert missing.status_code == 422  # cameras_on must be given


def test_children_are_the_parents_own_and_18_months_or_older(
    client, db_engine, finished_parent, free_sitter, child_of, user
):
    sitter = free_sitter()
    day = india_day(2)
    baby = child_of(finished_parent, name="Meera", born=date(day.year - 1, day.month, 1))
    response = book(client, finished_parent, sitter, child_ids=[str(baby)])
    assert response.status_code == 422 and response.json()["error"]["code"] == "child_too_young"

    stranger = uuid.uuid4()  # a child id that isn't theirs
    response = book(client, finished_parent, sitter, child_ids=[str(stranger)])
    assert response.status_code == 404
    kids = children_of(db_engine, finished_parent["id"])[:1]
    response = book(client, finished_parent, sitter, child_ids=kids * 2)
    assert response.status_code == 422 and response.json()["error"]["code"] == "child_repeated"


@pytest.mark.parametrize(
    ("born", "on", "months"),
    [
        (date(2025, 5, 18), date(2026, 11, 18), 18),
        (date(2025, 5, 19), date(2026, 11, 18), 17),  # turns 18 months tomorrow
        (date(2025, 5, 31), date(2026, 11, 30), 17),
        (date(2024, 2, 29), date(2026, 2, 28), 23),
    ],
)
def test_months_old(born, on, months):
    assert bookings._months_old(born, on) == months


def test_turning_18_months_counts_on_the_booking_day(client, db_engine, finished_parent, free_sitter, child_of):
    sitter = free_sitter()
    day = india_day(2)
    born = date(day.year - 1 if day.month > 6 else day.year - 2, (day.month - 6 - 1) % 12 + 1, 1)
    child = child_of(finished_parent, name="Kavya", born=born)
    assert book(client, finished_parent, sitter, child_ids=[str(child)]).status_code == 201


def test_only_confirmed_bookings_take_her_time(client, db_engine, finished_parent, free_sitter, child_of):
    sitter = free_sitter("recharge")
    kids = children_of(db_engine, finished_parent["id"])
    first = book(client, finished_parent, sitter, child_ids=kids)
    # No slot hold while payment is pending (decided 2026-11-03): the same time can be booked again.
    second = book(client, finished_parent, sitter, child_ids=kids)
    assert first.status_code == second.status_code == 201

    with db_engine.begin() as conn:
        conn.execute(text("UPDATE bookings SET status = 'confirmed' WHERE id = :id"), {"id": first.json()["id"]})
    third = book(client, finished_parent, sitter, child_ids=kids)
    assert third.status_code == 409 and third.json()["error"]["code"] == "not_free"
    found = options(client, finished_parent, sitter)
    taken = (at(india_day(2), 10), at(india_day(2), 12))
    for item in found["times"]:
        start, end = datetime.fromisoformat(item["starts_at"]), datetime.fromisoformat(item["ends_at"])
        assert end <= taken[0] or start >= taken[1]
    assert found["first_booking"] is False


def test_a_child_with_bookings_cant_be_removed(client, db_engine, finished_parent, free_sitter, child_of):
    sitter = free_sitter()
    child = child_of(finished_parent)
    assert book(client, finished_parent, sitter, child_ids=[str(child)]).status_code == 201
    response = client.delete(f"/parent/children/{child}", headers=auth_for(finished_parent))
    assert response.status_code == 409 and response.json()["error"]["code"] == "child_has_bookings"


def test_unfinished_parents_cant_book(client, parent, free_sitter):
    sitter = free_sitter()
    response = book(client, parent, sitter, child_ids=[str(uuid.uuid4())])
    assert response.status_code == 409 and response.json()["error"]["code"] == "profile_unfinished"


def test_hidden_sitters_cant_be_booked(client, db_engine, finished_parent, make_sitter):
    hidden = make_sitter(live=False)
    kids = children_of(db_engine, finished_parent["id"])
    response = book(client, finished_parent, hidden, child_ids=kids)
    assert response.status_code == 404
