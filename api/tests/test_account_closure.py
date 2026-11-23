# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Closing their own account, and data requests (CLAUDE.md 6.13; phase 10, Reuben 2026-11-23).

A parent or sitter closes their account once nothing is booked ahead or under way, and a parent owes
nothing; a sitter's pay still due is paid as usual. A closed account can't use the app and isn't shown;
an admin can reopen it. Data requests (access, correction, deletion) are complaints an admin handles by hand.
"""

from sqlalchemy import text

from tests.test_account_status import act, profile_status
from tests.test_admin_payments import confirm, paid, verify_children  # noqa: F401
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_cancellations import confirmed, to  # noqa: F401  (fixture)
from tests.test_documents import admin, as_user, client, parent, row, scalar, storage  # noqa: F401
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_payment_history import charge
from tests.test_payments import booking  # noqa: F401  (fixture)
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, user  # noqa: F401  (fixture)
from tests.test_sitter_bookings import signed_in
from tests.test_verification import reviewer  # noqa: F401  (fixture)


def closing(client, who):
    response = client.get("/me/closing", headers=auth_for(who))
    assert response.status_code == 200, response.text
    return response.json()


def close(client, who, reason=None):
    return client.post("/me/close", json={"reason": reason}, headers=auth_for(who))


def test_a_parent_with_nothing_booked_closes_their_account(client, db_engine, mailbox, finished_parent):
    assert closing(client, finished_parent) == {"can_close": True, "reasons": [], "owed_paise": 0, "pay_due_paise": 0}
    mailbox.sent.clear()
    done = close(client, finished_parent, reason="  Moving away.  ")
    assert done.status_code == 200 and done.json() == {"status": "closed"}
    assert profile_status(db_engine, finished_parent["id"]) == "closed"
    action = row(
        db_engine,
        "SELECT action, kind, reason, admin_id FROM account_actions WHERE profile_id = :p",
        p=finished_parent["id"],
    )
    assert dict(action) == {"action": "closed", "kind": None, "reason": "Moving away.", "admin_id": None}
    assert (
        scalar(
            db_engine,
            "SELECT count(*) FROM audit_log WHERE action = 'account_closed' AND entity_id = :p",
            p=str(finished_parent["id"]),
        )
        == 1
    )
    (told,) = to(mailbox, finished_parent["email"])
    assert told.subject == "Your Pacifyco account is closed" and "earned" not in told.body

    # Closed: the app can't be used, there's nothing to appeal, and it can't be closed twice.
    blocked = client.get("/parent/bookings", headers=auth_for(finished_parent))
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "account_blocked"
    assert client.get("/me", headers=auth_for(finished_parent)).json()["profile"]["status"] == "closed"
    appeal = client.get("/me/appeal", headers=auth_for(finished_parent)).json()
    assert appeal["decision"] is None and appeal["can_appeal"] is False
    assert close(client, finished_parent).status_code == 403


def test_not_while_a_booking_is_ahead(client, db_engine, booking, finished_parent):
    found = closing(client, finished_parent)
    assert found["can_close"] is False and "coming up" in found["reasons"][0]
    refused = close(client, finished_parent)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "cannot_close_yet"
    assert profile_status(db_engine, finished_parent["id"]) != "closed"
    sitter = signed_in(db_engine, booking["sitter_id"])
    assert closing(client, sitter)["can_close"] is False  # the sitter has it ahead too


def test_not_while_a_parent_owes_money(client, db_engine, booking, finished_parent):
    charge(db_engine, booking, finished_parent["id"], amount=69_900)
    with db_engine.begin() as conn:  # the booking itself is over, so only the charge stands in the way
        conn.execute(text("UPDATE bookings SET status = 'cancelled_parent_late' WHERE id = :b"), {"b": booking["id"]})
    found = closing(client, finished_parent)
    assert found["owed_paise"] == 69_900
    assert found["reasons"] == ["You owe a payment to Pacifyco. Please pay it first."]


def test_a_sitter_closes_and_is_still_paid(client, db_engine, mailbox, confirmed, finished_parent):
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    with db_engine.begin() as conn:  # the booking is done, and her pay for it is waiting
        conn.execute(text("UPDATE bookings SET status = 'completed' WHERE id = :b"), {"b": confirmed["id"]})
        conn.execute(
            text(
                "INSERT INTO sitter_earnings (sitter_id, booking_id, kind, amount_paise, minutes, status)"
                " VALUES (:s, :b, 'booking', 60000, 120, 'held')"
            ),
            {"s": sitter["id"], "b": confirmed["id"]},
        )
    assert closing(client, sitter) == {"can_close": True, "reasons": [], "owed_paise": 0, "pay_due_paise": 60_000}
    mailbox.sent.clear()
    assert close(client, sitter).status_code == 200
    assert "₹600" in to(mailbox, sitter["email"])[-1].body
    assert scalar(db_engine, "SELECT status FROM sitter_earnings WHERE booking_id = :b", b=confirmed["id"]) == "held"
    reason = scalar(db_engine, "SELECT reason FROM account_actions WHERE profile_id = :p", p=sitter["id"])
    assert reason == "Closed by them."


def test_an_admin_reopens_it_but_cant_suspend_it(client, db_engine, mailbox, reviewer, finished_parent):
    assert close(client, finished_parent).status_code == 200
    suspend = act(client, reviewer, finished_parent["id"], "suspend")
    assert suspend.status_code == 409 and suspend.json()["error"]["code"] == "account_closed"
    account = client.get(f"/admin/accounts/{finished_parent['id']}", headers=as_user(reviewer)).json()
    assert account["status"] == "closed" and account["history"][0]["action"] == "closed"
    assert account["history"][0]["by"] is None
    reopened = act(client, reviewer, finished_parent["id"], "reinstate", reason="They asked to come back.")
    assert reopened.status_code == 200, reopened.text
    assert profile_status(db_engine, finished_parent["id"]) in ("active", "pending")


def test_admins_cant_close_through_here(client, admin):
    assert client.get("/me/closing", headers=as_user(admin)).status_code == 403
    assert client.post("/me/close", json={}, headers=as_user(admin)).status_code == 403


# ---------- data requests ----------


def test_a_data_request_says_what_its_for(client, reviewer, booking, finished_parent):
    bare = client.post(
        "/me/complaints",
        json={"type": "data_request", "description": "Please delete my data."},
        headers=auth_for(finished_parent),
    )
    assert bare.status_code == 422 and bare.json()["error"]["code"] == "request_kind"
    stray = client.post(
        "/me/complaints",
        json={"type": "payment", "description": "x", "request_kind": "access"},
        headers=auth_for(finished_parent),
    )
    assert stray.status_code == 422

    made = client.post(
        "/me/complaints",
        json={
            "type": "data_request",
            "request_kind": "deletion",
            "description": "Please delete my data.",
            "booking_id": booking["id"],
        },
        headers=auth_for(finished_parent),
    )
    assert made.status_code == 201, made.text
    body = made.json()
    assert body["request_kind"] == "deletion" and body["booking_id"] is None  # about their data, not a booking
    listed = client.get("/admin/complaints", headers=as_user(reviewer)).json()
    (row_,) = [item for item in listed if item["id"] == body["id"]]
    assert row_["type"] == "data_request" and row_["request_kind"] == "deletion"
    seen = client.get(f"/admin/complaints/{body['id']}", headers=as_user(reviewer)).json()
    assert seen["request_kind"] == "deletion"
    done = client.post(
        f"/admin/complaints/{body['id']}/resolve",
        json={"body": "Deleted, except what the law requires us to keep."},
        headers=as_user(reviewer),
    )
    assert done.json()["status"] == "resolved"
