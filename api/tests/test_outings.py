# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Outings (CLAUDE.md 6.1 and 6.4; Reuben, 2026-11-21).

Recharge only. The parent sets one up when booking (where the family will be), so the sitter knows before
she accepts that she'll meet them there, not at home; the exact address goes in the chat. The parent can add,
change or remove it until the start; a sitter who has accepted is told.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from tests.test_admin_payments import verify_children  # noqa: F401
from tests.test_auto_cancel import move
from tests.test_bookings import book, child_of, children_of, free_sitter, options  # noqa: F401  (fixtures)
from tests.test_documents import admin, client, parent, row, rows, scalar, storage  # noqa: F401  (fixtures)
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_payments import get  # noqa: F401
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import auth_for, user  # noqa: F401  (fixture)


def kids(db_engine, who):
    return children_of(db_engine, who["id"])[:1]


def set_outing(client, who, booking_id, where):
    return client.put(f"/parent/bookings/{booking_id}/outing", json={"outing_where": where}, headers=auth_for(who))


def test_only_recharge_bookings_can_have_an_outing(client, db_engine, finished_parent, free_sitter):
    unwind = free_sitter("unwind")
    assert options(client, finished_parent, unwind)["outings_allowed"] is False
    response = book(
        client, finished_parent, unwind, child_ids=kids(db_engine, finished_parent), outing_where="Cubbon Park"
    )
    assert response.status_code == 422 and response.json()["error"]["code"] == "no_outings"
    recharge = free_sitter("recharge")
    assert options(client, finished_parent, recharge)["outings_allowed"] is True


def test_the_sitter_sees_the_outing_before_she_accepts(client, db_engine, finished_parent, free_sitter):
    verify_children(db_engine, finished_parent["id"])
    sitter = free_sitter("recharge")
    made = book(
        client,
        finished_parent,
        sitter,
        child_ids=kids(db_engine, finished_parent),
        outing_where="  Cubbon Park, then home ",
    )
    assert made.status_code == 201, made.text
    assert made.json()["outing_where"] == "Cubbon Park, then home"
    (request,) = client.get("/sitter/requests", headers=auth_for(sitter)).json()
    assert request["outing_where"] == "Cubbon Park, then home"
    detail = client.get(f"/sitter/bookings/{made.json()['id']}", headers=auth_for(sitter)).json()
    assert detail["outing_where"] == "Cubbon Park, then home"


def test_no_outing_by_default(client, db_engine, finished_parent, free_sitter):
    made = book(client, finished_parent, free_sitter("recharge"), child_ids=kids(db_engine, finished_parent))
    assert made.json()["outing_where"] is None


def test_the_parent_changes_it_until_the_start_and_an_accepted_sitter_is_told(
    client, db_engine, mailbox, finished_parent, free_sitter
):
    sitter = free_sitter("recharge")
    made = book(client, finished_parent, sitter, child_ids=kids(db_engine, finished_parent)).json()
    # Still a request: changed quietly.
    response = set_outing(client, finished_parent, made["id"], "Lalbagh")
    assert response.status_code == 200 and response.json()["outing_where"] == "Lalbagh"
    assert [e for e in mailbox.sent if e.to == sitter["email"] and "outing" in e.heading] == []

    with db_engine.begin() as conn:  # she has accepted
        conn.execute(text("UPDATE bookings SET status = 'confirmed' WHERE id = :b"), {"b": made["id"]})
    assert set_outing(client, finished_parent, made["id"], "Cubbon Park").status_code == 200
    told = [e for e in mailbox.sent if e.to == sitter["email"]][-1]
    assert told.heading == "The family has changed the outing." and "Cubbon Park" in told.body
    assert set_outing(client, finished_parent, made["id"], None).json()["outing_where"] is None
    assert "removed the outing" in [e for e in mailbox.sent if e.to == sitter["email"]][-1].body

    audit = rows(db_engine, "SELECT after FROM audit_log WHERE action = 'outing_set' AND entity_id = :b", b=made["id"])
    assert [item["after"]["outing_where"] for item in audit] == ["Lalbagh", "Cubbon Park", None]

    move(db_engine, made["id"], datetime.now(UTC) - timedelta(minutes=5))
    late = set_outing(client, finished_parent, made["id"], "Somewhere")
    assert late.status_code == 409 and late.json()["error"]["code"] == "outing_locked"


def test_not_on_other_plans_or_other_peoples_bookings(client, db_engine, finished_parent, free_sitter):
    made = book(client, finished_parent, free_sitter("unwind"), child_ids=kids(db_engine, finished_parent)).json()
    response = set_outing(client, finished_parent, made["id"], "Park")
    assert response.status_code == 422 and response.json()["error"]["code"] == "no_outings"
    assert set_outing(client, finished_parent, uuid.uuid4(), "Park").status_code == 404
