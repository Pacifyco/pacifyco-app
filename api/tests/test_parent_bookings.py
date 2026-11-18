# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""The parent's bookings list (CLAUDE.md 6.4; phase 7 "Parent booking lists").

Every booking the parent has made: upcoming ones (on their way, not yet ended) soonest first, and the rest
(ended or cancelled) most recent first. Only theirs, and never the plan's name. Overdue unpaid or
unverified bookings are cancelled when the list is opened, as when one booking is opened."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from tests.test_auto_cancel import move, status
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_documents import admin, as_user, cleanup_documents, client, parent, row, rows, scalar, storage  # noqa: F401
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_payments import booking, pay  # noqa: F401  (fixture)
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, user  # noqa: F401  (fixture)


def listed(client, who):
    response = client.get("/parent/bookings", headers=auth_for(who))
    assert response.status_code == 200, response.text
    return response.json()


def test_nothing_yet(client, finished_parent):
    assert listed(client, finished_parent) == {"upcoming": [], "past": []}


def test_a_new_booking_is_upcoming(client, db_engine, booking, finished_parent):
    found = listed(client, finished_parent)
    assert found["past"] == []
    (item,) = found["upcoming"]
    assert item == {
        "id": booking["id"],
        "sitter_id": booking["sitter_id"],
        "sitter_name": "Lakshmi Nair",
        "starts_at": booking["starts_at"],
        "ends_at": booking["ends_at"],
        "hours": booking["hours"],
        "children": booking["children"],
        "price_paise": booking["price_paise"],
        "status": "pending_payment",
        "pay_by": booking["pay_by"],
        "payment_sent": False,
    }
    assert "plan" not in str(found).lower()  # never the plan's name (6.1)

    assert pay(client, finished_parent, booking["id"]).status_code == 201
    assert listed(client, finished_parent)["upcoming"][0]["payment_sent"] is True


def test_upcoming_soonest_first_and_past_most_recent_first(client, db_engine, finished_parent, free_sitter):
    kids = children_of(db_engine, finished_parent["id"])[:1]
    sitter = free_sitter("unwind")

    def made():
        response = book(client, finished_parent, sitter, child_ids=kids, hours=1)
        assert response.status_code == 201, response.text
        return response.json()["id"]

    later, sooner, ended, older_ended, cancelled = (made() for _ in range(5))
    now = datetime.now(UTC)
    move(db_engine, later, now + timedelta(days=3), 1)
    move(db_engine, sooner, now + timedelta(days=2), 1)
    move(db_engine, ended, now - timedelta(days=1), 1)
    move(db_engine, older_ended, now - timedelta(days=5), 1)
    move(db_engine, cancelled, now + timedelta(days=4), 1)
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE bookings SET status = 'confirmed' WHERE id IN (:a, :b)"), {"a": ended, "b": older_ended}
        )
        conn.execute(text("UPDATE bookings SET status = 'cancelled_parent' WHERE id = :c"), {"c": cancelled})

    found = listed(client, finished_parent)
    assert [item["id"] for item in found["upcoming"]] == [sooner, later]
    assert [item["id"] for item in found["past"]] == [cancelled, ended, older_ended]


def test_an_overdue_unpaid_booking_is_cancelled_when_the_list_opens(client, db_engine, booking, finished_parent):
    move(db_engine, booking["id"], datetime.now(UTC) + timedelta(hours=2))
    found = listed(client, finished_parent)
    assert found["upcoming"] == []
    assert found["past"][0]["id"] == booking["id"] and found["past"][0]["status"] == "cancelled_unpaid"
    assert status(db_engine, booking["id"]) == "cancelled_unpaid"


def test_only_their_own_bookings(client, db_engine, booking, finished_parent):
    other = {"id": uuid.uuid4(), "email": f"{uuid.uuid4()}@example.com"}
    try:
        assert client.post("/me/profile", json=PARENT, headers=auth_for(other)).status_code == 201
        assert listed(client, other) == {"upcoming": [], "past": []}
    finally:
        cleanup_documents(db_engine, other["id"])


def test_sitters_and_admins_cant_open_it(client, admin):
    assert client.get("/parent/bookings", headers=as_user(admin)).status_code == 403
