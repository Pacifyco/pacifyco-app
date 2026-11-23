# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""User management (phase 10; Reuben, 2026-11-22): suspend, remove and reinstate parents and sitters.

Each has a kind of reason and the reason itself, which the person is emailed. Their upcoming bookings are
cancelled and refunded (no strike) and the other side told. A low-ratings decision waits for her response
or the end of her 12 hours (6.11); the other kinds don't. Reinstating needs fewer than 5 counting strikes.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from tests.test_admin_payments import confirm, paid, verify_children  # noqa: F401
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_cancellations import confirmed, payments_of, to  # noqa: F401  (fixture)
from tests.test_documents import admin, as_user, client, parent, row, rows, scalar, storage  # noqa: F401
from tests.test_incidents import ADMINS, admins_told, emergency  # noqa: F401  (fixture)
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_payments import booking  # noqa: F401  (fixture)
from tests.test_reviews import done, flagged, review, sitter_of  # noqa: F401  (fixtures)
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, user  # noqa: F401  (fixture)
from tests.test_sitter_bookings import signed_in
from tests.test_verification import reviewer  # noqa: F401  (fixture)


def act(client, admin_id, profile_id, action, kind="safety", reason="A serious report about a booking."):
    body = {"reason": reason} if action == "reinstate" else {"kind": kind, "reason": reason}
    return client.post(f"/admin/accounts/{profile_id}/{action}", json=body, headers=as_user(admin_id))


def account(client, admin_id, profile_id):
    response = client.get(f"/admin/accounts/{profile_id}", headers=as_user(admin_id))
    assert response.status_code == 200, response.text
    return response.json()


def booking_status(db_engine, booking_id):
    return scalar(db_engine, "SELECT status FROM bookings WHERE id = :b", b=booking_id)


def profile_status(db_engine, profile_id):
    return scalar(db_engine, "SELECT status FROM profiles WHERE id = :p", p=profile_id)


# ---------- suspending and removing ----------


def test_suspending_a_sitter_cancels_and_refunds_her_bookings(
    client, db_engine, mailbox, admins_told, reviewer, confirmed, finished_parent
):
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    before = account(client, reviewer, sitter["id"])
    assert before["status"] == "active" and before["upcoming_bookings"] == 1 and before["history"] == []
    mailbox.sent.clear()

    done = act(client, reviewer, sitter["id"], "suspend", reason="A family reported a theft.")
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "suspended" and done.json()["upcoming_bookings"] == 0
    assert booking_status(db_engine, confirmed["id"]) == "cancelled_by_admin"
    refunds = payments_of(db_engine, confirmed["id"], "refund")
    assert len(refunds) == 1 and refunds[0]["amount_paise"] == -confirmed["price_paise"]
    assert refunds[0]["status"] == "pending"
    strikes = scalar(db_engine, "SELECT count(*) FROM strikes WHERE sitter_id = :s", s=sitter["id"])
    assert strikes == 0

    told = to(mailbox, sitter["email"])
    assert [email.subject for email in told] == ["Your Pacifyco account is suspended"]
    assert "The reason: A family reported a theft." in told[0].body and "15 days" in told[0].body
    family = to(mailbox, finished_parent["email"])
    assert [email.subject for email in family] == ["Pacifyco has cancelled your booking"]
    assert "refund you in full" in family[0].body and "theft" not in family[0].body
    alerts = [email for email in mailbox.sent if email.subject == "Families need another sitter"]
    assert sorted(email.to for email in alerts) == sorted(ADMINS)

    blocked = client.get("/sitter/bookings", headers=auth_for(sitter))
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "account_blocked"
    history = account(client, reviewer, sitter["id"])["history"]
    assert [(item["action"], item["kind"], item["reason"]) for item in history] == [
        ("suspended", "safety", "A family reported a theft.")
    ]
    assert history[0]["by"] is not None
    audit = rows(
        db_engine, "SELECT action FROM audit_log WHERE entity_id = :e ORDER BY created_at", e=str(sitter["id"])
    )
    assert "account_suspended" in [item["action"] for item in audit]


def test_reinstating_makes_her_active_again(client, db_engine, mailbox, reviewer, confirmed):
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    assert act(client, reviewer, sitter["id"], "remove").status_code == 200
    assert profile_status(db_engine, sitter["id"]) == "removed"
    mailbox.sent.clear()

    back = act(client, reviewer, sitter["id"], "reinstate", reason="We looked into it: it wasn't her.")
    assert back.status_code == 200, back.text
    assert back.json()["status"] == "active"  # she was approved
    assert [item["action"] for item in back.json()["history"]] == ["reinstated", "removed"]
    told = to(mailbox, sitter["email"])
    assert [email.subject for email in told] == ["Your Pacifyco account is active again"]
    assert "it wasn't her" in told[0].body
    assert client.get("/sitter/bookings", headers=auth_for(sitter)).status_code == 200
    # Her cancelled booking stays cancelled.
    assert booking_status(db_engine, confirmed["id"]) == "cancelled_by_admin"


def test_removing_a_parent_cancels_their_bookings_and_tells_the_sitter(
    client, db_engine, mailbox, reviewer, confirmed, finished_parent
):
    with db_engine.begin() as conn:  # she could see it
        conn.execute(text("UPDATE bookings SET request_visible_at = now() WHERE id = :b"), {"b": confirmed["id"]})
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    mailbox.sent.clear()
    done = act(client, reviewer, finished_parent["id"], "remove", kind="other", reason="Abusive to a sitter.")
    assert done.status_code == 200, done.text
    assert booking_status(db_engine, confirmed["id"]) == "cancelled_by_admin"
    assert len(payments_of(db_engine, confirmed["id"], "refund")) == 1

    told = to(mailbox, finished_parent["email"])
    assert [email.subject for email in told] == ["Your Pacifyco account has been removed"]
    assert "Abusive to a sitter." in told[0].body
    hers = to(mailbox, sitter["email"])
    assert [email.subject for email in hers] == ["A booking was cancelled"]
    assert "Abusive" not in hers[0].body and "no strike" in hers[0].body
    assert not [email for email in mailbox.sent if email.subject == "Families need another sitter"]

    blocked = client.get("/parent/bookings", headers=auth_for(finished_parent))
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "account_blocked"

    verified = scalar(
        db_engine, "SELECT verification_status FROM parents WHERE profile_id = :p", p=finished_parent["id"]
    )
    back = act(client, reviewer, finished_parent["id"], "reinstate", reason="Agreed after a call.")
    assert back.json()["status"] == ("active" if verified == "approved" else "pending")


def test_a_booking_under_way_is_left_for_an_admin(client, db_engine, reviewer, confirmed):
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE bookings SET status = 'in_progress', starts_at = :s, ends_at = :e WHERE id = :b"),
            {
                "s": datetime.now(UTC) - timedelta(minutes=30),
                "e": datetime.now(UTC) + timedelta(hours=1),
                "b": confirmed["id"],
            },
        )
    sitter_id = confirmed["sitter_id"]
    found = account(client, reviewer, sitter_id)
    assert found["upcoming_bookings"] == 0 and found["under_way_bookings"] == 1
    assert act(client, reviewer, sitter_id, "suspend").status_code == 200
    assert booking_status(db_engine, confirmed["id"]) == "in_progress"


def test_reasons_states_and_who(client, db_engine, reviewer, finished_parent):
    person = finished_parent["id"]
    blank = act(client, reviewer, person, "suspend", reason="   ")
    assert blank.status_code == 422 and blank.json()["error"]["code"] == "reason_required"
    unknown = client.post(
        f"/admin/accounts/{person}/suspend", json={"kind": "bad", "reason": "x"}, headers=as_user(reviewer)
    )
    assert unknown.status_code == 422
    not_blocked = act(client, reviewer, person, "reinstate")
    assert not_blocked.status_code == 409 and not_blocked.json()["error"]["code"] == "not_blocked"

    assert act(client, reviewer, person, "suspend").status_code == 200
    twice = act(client, reviewer, person, "suspend")
    assert twice.status_code == 409 and twice.json()["error"]["code"] == "already_blocked"
    assert act(client, reviewer, person, "remove").status_code == 200  # a suspended account can be removed
    again = act(client, reviewer, person, "remove")
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_removed"

    admin_target = act(client, reviewer, reviewer, "suspend")
    assert admin_target.status_code == 404
    # Low ratings is for sitters only.
    assert act(client, reviewer, person, "reinstate").status_code == 200
    ratings = act(client, reviewer, person, "suspend", kind="low_ratings")
    assert ratings.status_code == 409 and ratings.json()["error"]["code"] == "ratings_not_decidable"


def test_admins_only(client, finished_parent):
    headers = auth_for(finished_parent)
    for path in ("people", f"accounts/{finished_parent['id']}"):
        assert client.get(f"/admin/{path}", headers=headers).status_code == 403
    for action in ("suspend", "remove", "reinstate"):
        response = client.post(
            f"/admin/accounts/{finished_parent['id']}/{action}",
            json={"kind": "other", "reason": "x"},
            headers=headers,
        )
        assert response.status_code == 403


# ---------- low ratings wait for her response (6.11) ----------


def test_a_low_ratings_removal_waits_for_her_response(client, db_engine, reviewer, done, flagged):
    sitter = sitter_of(db_engine, done["id"])
    untold = act(client, reviewer, sitter["id"], "remove", kind="low_ratings", reason="Low ratings.")
    assert untold.status_code == 409 and untold.json()["error"]["code"] == "ratings_not_decidable"
    assert "Tell her the reason" in account(client, reviewer, sitter["id"])["ratings_wait"]

    told = client.post(f"/admin/rating-flags/{flagged}/tell", json={"reason": "Low"}, headers=as_user(reviewer))
    assert told.status_code == 200
    waiting = act(client, reviewer, sitter["id"], "remove", kind="low_ratings", reason="Low ratings.")
    assert waiting.status_code == 409 and "12 hours" in waiting.json()["error"]["message"]

    answered = client.post(
        f"/sitter/rating-flags/{flagged}/respond", json={"response": "I was ill that week."}, headers=auth_for(sitter)
    )
    assert answered.status_code == 200, answered.text
    assert account(client, reviewer, sitter["id"])["ratings_wait"] is None
    removed = act(client, reviewer, sitter["id"], "remove", kind="low_ratings", reason="Low ratings.")
    assert removed.status_code == 200, removed.text
    assert removed.json()["status"] == "removed"


def test_a_low_ratings_removal_after_her_12_hours(client, db_engine, reviewer, done, flagged):
    sitter = sitter_of(db_engine, done["id"])
    client.post(f"/admin/rating-flags/{flagged}/tell", json={"reason": "Low"}, headers=as_user(reviewer))
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE rating_flags SET told_at = now() - interval '12 hours 1 minute' WHERE id = :f"), {"f": flagged}
        )
    assert act(client, reviewer, sitter["id"], "suspend", kind="low_ratings").status_code == 200


def test_other_kinds_dont_wait(client, db_engine, reviewer, done, flagged):
    sitter = sitter_of(db_engine, done["id"])
    assert act(client, reviewer, sitter["id"], "remove", kind="safety").status_code == 200


# ---------- strikes and incidents ----------


def test_five_strikes_remove_her_and_block_reinstating(client, db_engine, reviewer, free_sitter):
    sitter = free_sitter("pause")
    for _ in range(5):
        given = client.post(
            f"/admin/sitters/{sitter['id']}/strikes", json={"reason": "Late again."}, headers=as_user(reviewer)
        )
        assert given.status_code == 201, given.text
    found = account(client, reviewer, sitter["id"])
    assert found["status"] == "removed" and found["five_strikes"] is True
    assert [(item["action"], item["kind"]) for item in found["history"]] == [("removed", "strikes")]

    refused = act(client, reviewer, sitter["id"], "reinstate")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "five_strikes"
    strike_id = scalar(db_engine, "SELECT id FROM strikes WHERE sitter_id = :s LIMIT 1", s=sitter["id"])
    removed = client.post(
        f"/admin/strikes/{strike_id}/remove", json={"reason": "Doctor's note"}, headers=as_user(reviewer)
    )
    assert removed.status_code == 200
    assert act(client, reviewer, sitter["id"], "reinstate").json()["status"] == "active"


def test_a_theft_report_suspension_is_in_her_history(client, db_engine, reviewer, confirmed, finished_parent):
    with db_engine.begin() as conn:  # under way
        conn.execute(
            text("UPDATE bookings SET starts_at = :s, ends_at = :e WHERE id = :b"),
            {
                "s": datetime.now(UTC) - timedelta(minutes=5),
                "e": datetime.now(UTC) + timedelta(hours=2),
                "b": confirmed["id"],
            },
        )
    assert emergency(client, finished_parent, confirmed["id"], "theft").status_code == 201
    history = account(client, reviewer, confirmed["sitter_id"])["history"]
    assert [(item["action"], item["kind"], item["by"]) for item in history] == [("suspended", "safety", None)]


# ---------- finding people ----------


def test_people_by_name_email_or_phone(client, db_engine, reviewer, finished_parent, free_sitter):
    sitter = free_sitter("pause")
    person = row(db_engine, "SELECT full_name, email, phone FROM profiles WHERE id = :p", p=finished_parent["id"])

    def found(**params):
        response = client.get("/admin/people", params=params, headers=as_user(reviewer))
        assert response.status_code == 200, response.text
        return [item["id"] for item in response.json()]

    assert str(finished_parent["id"]) in found(q=person["email"])
    assert str(finished_parent["id"]) in found(q=person["email"].upper())
    assert str(finished_parent["id"]) in found(q=person["phone"][-6:])
    assert str(finished_parent["id"]) not in found(q=person["email"], role="sitter")
    assert str(sitter["id"]) in found(role="sitter", status="active")
    assert str(reviewer) not in found(q="")  # never admins
    assert found(q="%_%_%_%_%-no-one") == []  # wildcards are taken literally
