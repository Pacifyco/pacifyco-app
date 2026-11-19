# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""The sitter's bookings list (CLAUDE.md 6.2, 6.4; phase 7 "Sitter booking lists").

Only bookings that were confirmed: never one waiting for payment or a child's verification, nor one
cancelled before it was confirmed. Upcoming soonest first, the rest most recent first. Never the price the
parent paid or the plan's name: her pay for the booked hours (level pay × hours, whatever the number of
children)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from tests.test_auto_cancel import move
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_documents import admin, as_user, cleanup_documents, client, parent, row, rows, scalar, storage  # noqa: F401
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_payments import booking, pay  # noqa: F401  (fixture)
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import auth_for, user  # noqa: F401  (fixture)


def signed_in(db_engine, profile_id):
    return {
        "id": uuid.UUID(str(profile_id)),
        "email": scalar(db_engine, "SELECT email FROM profiles WHERE id = :i", i=profile_id),
    }


def listed(client, who):
    response = client.get("/sitter/bookings", headers=auth_for(who))
    assert response.status_code == 200, response.text
    return response.json()


def set_status(db_engine, booking_id, status):
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE bookings SET status = :s WHERE id = :b"), {"s": status, "b": booking_id})


def test_only_bookings_she_accepted_show(client, db_engine, booking, finished_parent):
    sitter = signed_in(db_engine, booking["sitter_id"])
    # Accepted and waiting for the family to pay (the fixture's state): shown, without the address.
    (waiting,) = listed(client, sitter)["upcoming"]
    assert waiting["status"] == "pending_payment"
    hidden = (
        "requested",  # a request is in her requests, not her bookings
        "request_declined",
        "request_lapsed",
        "awaiting_verification",
        "cancelled_slot_taken",
        "cancelled_unverified",
    )
    for status in hidden:
        set_status(db_engine, booking["id"], status)
        assert listed(client, sitter) == {"upcoming": [], "past": []}, status
    set_status(db_engine, booking["id"], "cancelled_unpaid")  # she accepted, the family didn't pay
    assert [item["status"] for item in listed(client, sitter)["past"]] == ["cancelled_unpaid"]

    set_status(db_engine, booking["id"], "confirmed")
    found = listed(client, sitter)
    assert found["past"] == []
    (item,) = found["upcoming"]
    parent_name = scalar(db_engine, "SELECT full_name FROM profiles WHERE id = :p", p=finished_parent["id"])
    assert item == {
        "id": booking["id"],
        "starts_at": booking["starts_at"],
        "ends_at": booking["ends_at"],
        "hours": 2,
        "family_name": parent_name.split()[0],
        "children": booking["children"],
        "bath_time": False,
        "cameras_on": booking["cameras_on"],
        "camera_locations": booking["camera_locations"],
        "pay_paise": 2 * 30_000,  # Unwind level pay, ₹300 an hour (6.2)
        "status": "confirmed",
        "answer_by": None,
    }
    text_seen = str(found).lower()
    assert "price" not in text_seen and "unwind" not in text_seen and "plan" not in text_seen
    assert str(booking["price_paise"]) not in str(found)


def test_upcoming_soonest_first_and_past_most_recent_first(client, db_engine, finished_parent, free_sitter):
    kids = children_of(db_engine, finished_parent["id"])[:1]
    sitter = free_sitter("unwind")

    def made(status, starts_in):
        response = book(client, finished_parent, sitter, child_ids=kids, hours=1)
        assert response.status_code == 201, response.text
        booking_id = response.json()["id"]
        move(db_engine, booking_id, datetime.now(UTC) + starts_in, 1)
        set_status(db_engine, booking_id, status)
        return booking_id

    later = made("confirmed", timedelta(days=3))
    sooner = made("confirmed", timedelta(days=2))
    done = made("completed", -timedelta(days=1))
    ended = made("confirmed", -timedelta(days=5))  # ended, not yet closed (phase 8)
    cancelled = made("cancelled_parent", timedelta(days=4))
    made("requested", timedelta(days=1))  # a request: in her requests, not here

    found = listed(client, sitter)
    assert [item["id"] for item in found["upcoming"]] == [sooner, later]
    assert [item["id"] for item in found["past"]] == [cancelled, done, ended]


def test_pay_is_the_same_whatever_the_number_of_children(client, db_engine, finished_parent, free_sitter, child_of):
    child_of(finished_parent)
    kids = children_of(db_engine, finished_parent["id"])
    assert len(kids) >= 2
    sitter = free_sitter("recharge")
    response = book(client, finished_parent, sitter, child_ids=kids[:2], hours=3)
    assert response.status_code == 201, response.text
    set_status(db_engine, response.json()["id"], "confirmed")
    (item,) = listed(client, sitter)["upcoming"]
    assert item["pay_paise"] == 3 * 40_000 and len(item["children"]) == 2


def test_only_her_own_bookings(client, db_engine, booking, free_sitter):
    set_status(db_engine, booking["id"], "confirmed")
    other = free_sitter("unwind")
    assert listed(client, other) == {"upcoming": [], "past": []}


def test_parents_and_admins_cant_open_it(client, finished_parent, admin):
    assert client.get("/sitter/bookings", headers=auth_for(finished_parent)).status_code == 403
    assert client.get("/sitter/bookings", headers=as_user(admin)).status_code == 403


# ---------- one booking ----------


def detail(client, who, booking_id):
    return client.get(f"/sitter/bookings/{booking_id}", headers=auth_for(who))


def test_a_confirmed_booking_shows_the_home_children_and_emergency_contact(client, db_engine, booking, finished_parent):
    sitter = signed_in(db_engine, booking["sitter_id"])
    child_id = children_of(db_engine, finished_parent["id"])[0]
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE children SET allergies = 'Peanuts', medical_notes = 'Inhaler at 6 pm', routines = 'Nap at 2'"
                " WHERE id = :c"
            ),
            {"c": child_id},
        )
    set_status(db_engine, booking["id"], "confirmed")
    response = detail(client, sitter, booking["id"])
    assert response.status_code == 200, response.text
    found = response.json()
    profile = row(db_engine, "SELECT address, pin_code FROM profiles WHERE id = :p", p=finished_parent["id"])
    assert found["address"] == profile["address"] and found["pin_code"] == profile["pin_code"]
    contact = row(
        db_engine,
        "SELECT name, relationship, phone FROM emergency_contacts WHERE parent_id = :p",
        p=finished_parent["id"],
    )
    assert found["emergency_contact"] == dict(contact)
    (child,) = found["children_details"]
    assert child["allergies"] == "Peanuts" and child["medical_notes"] == "Inhaler at 6 pm"
    assert child["routines"] == "Nap at 2" and child["age_months"] >= 18
    assert found["pay_paise"] == 2 * 30_000
    seen = str(found).lower()
    assert "price" not in seen and "unwind" not in seen and "plan" not in seen
    assert "certificate" not in seen and "verification" not in seen


def test_requests_she_cant_see_or_someone_elses_bookings_arent_found(client, db_engine, booking, free_sitter):
    sitter = signed_in(db_engine, booking["sitter_id"])
    for hidden in ("requested", "awaiting_verification", "cancelled_slot_taken", "request_lapsed"):
        set_status(db_engine, booking["id"], hidden)  # requested: no child verified, so she can't see it
        assert detail(client, sitter, booking["id"]).status_code == 404, hidden
    set_status(db_engine, booking["id"], "confirmed")
    assert detail(client, free_sitter("unwind"), booking["id"]).status_code == 404
    assert detail(client, sitter, uuid.uuid4()).status_code == 404


def test_past_or_cancelled_bookings_leave_out_the_address_and_contact(client, db_engine, booking):
    sitter = signed_in(db_engine, booking["sitter_id"])
    set_status(db_engine, booking["id"], "cancelled_parent")
    found = detail(client, sitter, booking["id"]).json()
    assert found["address"] is None and found["pin_code"] is None and found["emergency_contact"] is None
    set_status(db_engine, booking["id"], "confirmed")
    move(db_engine, booking["id"], datetime.now(UTC) - timedelta(days=1), 2)  # ended
    found = detail(client, sitter, booking["id"]).json()
    assert found["address"] is None and found["emergency_contact"] is None
    assert found["children_details"]  # still who she looked after


def test_parents_cant_open_it(client, booking, finished_parent):
    assert client.get(f"/sitter/bookings/{booking['id']}", headers=auth_for(finished_parent)).status_code == 403
