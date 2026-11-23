# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""The admin bookings overview and manual adjustments (phase 10; Reuben, 2026-11-23).

Every booking, filtered by group, name and date. On a booking an admin can cancel it (before the start,
refunded, no strike), refund part of it, add pay for the sitter, or waive an unpaid charge. Each needs a
reason, is audit logged and emails the people affected.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from tests.test_admin_payments import confirm, paid, verify_children  # noqa: F401
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_cancellations import confirmed, payments_of, to  # noqa: F401  (fixture)
from tests.test_documents import admin, as_user, client, parent, row, rows, scalar, storage  # noqa: F401
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_payments import booking  # noqa: F401  (fixture)
from tests.test_reviews import finish
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, user  # noqa: F401  (fixture)
from tests.test_sitter_bookings import signed_in
from tests.test_verification import reviewer  # noqa: F401  (fixture)


def listed(client, admin_id, **params):
    response = client.get("/admin/bookings", params=params, headers=as_user(admin_id))
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["bookings"]]


def detail(client, admin_id, booking_id):
    response = client.get(f"/admin/bookings/{booking_id}", headers=as_user(admin_id))
    assert response.status_code == 200, response.text
    return response.json()


def post(client, admin_id, path, **body):
    return client.post(f"/admin/{path}", json=body, headers=as_user(admin_id))


def a_charge(db_engine, booking, reference=None):
    with db_engine.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO payments (booking_id, parent_id, kind, amount_paise, status, upi_reference)"
                " SELECT id, parent_id, 'cancellation_charge', 69900, 'pending', :r FROM bookings WHERE id = :b"
                " RETURNING id"
            ),
            {"b": booking["id"], "r": reference},
        ).scalar_one()


# ---------- the overview ----------


def test_groups_names_and_dates(client, db_engine, reviewer, confirmed, finished_parent):
    booking_id = confirmed["id"]
    assert booking_id in listed(client, reviewer, group="upcoming")
    for group in ("under_way", "past", "cancelled"):
        assert booking_id not in listed(client, reviewer, group=group)
    name = scalar(db_engine, "SELECT full_name FROM profiles WHERE id = :p", p=finished_parent["id"])
    assert booking_id in listed(client, reviewer, q=name.split()[0].lower())
    assert listed(client, reviewer, q="%%no-one-is-called-this") == []
    starts = datetime.fromisoformat(confirmed["starts_at"]).astimezone(UTC)
    assert booking_id in listed(client, reviewer, starts_from=(starts - timedelta(days=1)).date().isoformat())
    assert booking_id not in listed(client, reviewer, starts_from=(starts + timedelta(days=2)).date().isoformat())

    with db_engine.begin() as conn:
        conn.execute(text("UPDATE bookings SET status = 'in_progress' WHERE id = :b"), {"b": booking_id})
    assert booking_id in listed(client, reviewer, group="under_way")
    finish(db_engine, booking_id)
    assert booking_id in listed(client, reviewer, group="past")

    bad = client.get("/admin/bookings", params={"group": "soon"}, headers=as_user(reviewer))
    assert bad.status_code == 422


def test_admins_only(client, confirmed, finished_parent):
    headers = auth_for(finished_parent)
    assert client.get("/admin/bookings", headers=headers).status_code == 403
    assert client.get(f"/admin/bookings/{confirmed['id']}", headers=headers).status_code == 403
    for path in ("cancel", "refund", "sitter-pay"):
        response = client.post(
            f"/admin/bookings/{confirmed['id']}/{path}", json={"reason": "x", "amount_paise": 100}, headers=headers
        )
        assert response.status_code == 403


# ---------- cancelling ----------


def test_cancelling_refunds_in_full_and_tells_both(client, db_engine, mailbox, reviewer, confirmed, finished_parent):
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    assert detail(client, reviewer, confirmed["id"])["can_cancel"] is True
    blank = post(client, reviewer, f"bookings/{confirmed['id']}/cancel", reason="  ")
    assert blank.status_code == 422
    mailbox.sent.clear()

    done = post(client, reviewer, f"bookings/{confirmed['id']}/cancel", reason="The family has a fever at home.")
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "cancelled_by_admin" and done.json()["can_cancel"] is False
    refunds = payments_of(db_engine, confirmed["id"], "refund")
    assert len(refunds) == 1 and refunds[0]["amount_paise"] == -confirmed["price_paise"]
    assert scalar(db_engine, "SELECT count(*) FROM strikes WHERE booking_id = :b", b=confirmed["id"]) == 0

    family = to(mailbox, finished_parent["email"])
    assert [email.subject for email in family] == ["Pacifyco has cancelled your booking"]
    assert "The reason: The family has a fever at home." in family[0].body and "refund you in full" in family[0].body
    hers = to(mailbox, sitter["email"])
    assert [email.subject for email in hers] == ["A booking was cancelled"] and "fever" in hers[0].body

    again = post(client, reviewer, f"bookings/{confirmed['id']}/cancel", reason="Again")
    assert again.status_code == 409 and again.json()["error"]["code"] == "cannot_cancel"


def test_a_booking_under_way_cant_be_cancelled(client, db_engine, reviewer, confirmed):
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE bookings SET status = 'in_progress', starts_at = now() - interval '10 minutes' WHERE id = :b"),
            {"b": confirmed["id"]},
        )
    refused = post(client, reviewer, f"bookings/{confirmed['id']}/cancel", reason="No")
    assert refused.status_code == 409


# ---------- refunding part ----------


def test_refunding_part_of_a_booking(client, db_engine, mailbox, reviewer, confirmed, finished_parent):
    price = confirmed["price_paise"]
    assert detail(client, reviewer, confirmed["id"])["refundable_paise"] == price
    mailbox.sent.clear()
    done = post(client, reviewer, f"bookings/{confirmed['id']}/refund", amount_paise=10_000, reason="She was late.")
    assert done.status_code == 200, done.text
    assert done.json()["refundable_paise"] == price - 10_000
    refunds = payments_of(db_engine, confirmed["id"], "refund")
    assert [(item["amount_paise"], item["status"]) for item in refunds] == [(-10_000, "pending")]
    assert done.json()["status"] == "confirmed"  # the booking itself goes ahead
    told = to(mailbox, finished_parent["email"])
    assert [email.subject for email in told] == ["Pacifyco is refunding you"]
    assert "₹100" in told[0].heading and "She was late." in told[0].body
    events = done.json()["history"]
    assert events[0]["action"] == "refund_owed" and events[0]["by"] is not None

    too_much = post(client, reviewer, f"bookings/{confirmed['id']}/refund", amount_paise=price, reason="All of it")
    assert too_much.status_code == 422 and too_much.json()["error"]["code"] == "refund_too_much"
    rest = post(client, reviewer, f"bookings/{confirmed['id']}/refund", amount_paise=price - 10_000, reason="The rest")
    assert rest.status_code == 200 and rest.json()["refundable_paise"] == 0
    none_left = post(client, reviewer, f"bookings/{confirmed['id']}/refund", amount_paise=100, reason="More")
    assert none_left.status_code == 409 and none_left.json()["error"]["code"] == "nothing_to_refund"


def test_nothing_to_refund_before_payment(client, reviewer, booking):
    refused = post(client, reviewer, f"bookings/{booking['id']}/refund", amount_paise=100, reason="Goodwill")
    assert refused.status_code == 409


# ---------- extra pay for the sitter ----------


def test_extra_pay_once_the_booking_is_over(client, db_engine, mailbox, reviewer, confirmed):
    sitter = signed_in(db_engine, confirmed["sitter_id"])
    early = post(client, reviewer, f"bookings/{confirmed['id']}/sitter-pay", amount_paise=20_000, reason="Bonus")
    assert early.status_code == 409 and early.json()["error"]["code"] == "booking_not_over"
    finish(db_engine, confirmed["id"])
    too_much = post(client, reviewer, f"bookings/{confirmed['id']}/sitter-pay", amount_paise=1_000_001, reason="x")
    assert too_much.status_code == 422
    mailbox.sent.clear()

    done = post(
        client, reviewer, f"bookings/{confirmed['id']}/sitter-pay", amount_paise=20_000, reason="Stayed for a storm."
    )
    assert done.status_code == 200, done.text
    extra = [item for item in done.json()["earnings"] if item["kind"] == "adjustment"]
    assert len(extra) == 1 and extra[0]["amount_paise"] == 20_000 and extra[0]["status"] == "released"
    due_by = datetime.fromisoformat(extra[0]["due_by"])
    assert timedelta(hours=11, minutes=59) < due_by - datetime.now(UTC) <= timedelta(hours=12)
    assert extra[0]["note"] == "Stayed for a storm."
    told = to(mailbox, sitter["email"])
    assert [email.subject for email in told] == ["Pacifyco has added to your pay"] and "₹200" in told[0].heading

    # More than one per booking, and she sees the note.
    again = post(client, reviewer, f"bookings/{confirmed['id']}/sitter-pay", amount_paise=5_000, reason="Correction")
    assert again.status_code == 200
    hers = client.get("/sitter/earnings", headers=auth_for(sitter)).json()["earnings"]
    assert sorted(item["note"] for item in hers if item["kind"] == "adjustment") == [
        "Correction",
        "Stayed for a storm.",
    ]


def test_extra_pay_on_a_cancelled_booking_is_due_at_once(client, db_engine, reviewer, confirmed):
    assert post(client, reviewer, f"bookings/{confirmed['id']}/cancel", reason="Rain").status_code == 200
    done = post(client, reviewer, f"bookings/{confirmed['id']}/sitter-pay", amount_paise=10_000, reason="Travel")
    assert done.status_code == 200, done.text
    assert [item["status"] for item in done.json()["earnings"]] == ["released"]


# ---------- waiving a charge ----------


def test_waiving_a_charge(client, db_engine, mailbox, reviewer, confirmed, finished_parent):
    charge = a_charge(db_engine, confirmed)
    owed = client.get("/parent/payments", headers=auth_for(finished_parent)).json()
    assert owed["owed_paise"] == 69_900
    assert next(item for item in detail(client, reviewer, confirmed["id"])["payments"] if item["id"] == str(charge))[
        "can_waive"
    ]
    mailbox.sent.clear()

    done = post(client, reviewer, f"charges/{charge}/waive", reason="A family emergency.")
    assert done.status_code == 200, done.text
    item = next(item for item in done.json()["payments"] if item["id"] == str(charge))
    assert item["status"] == "waived" and item["waive_reason"] == "A family emergency." and item["can_waive"] is False
    after = client.get("/parent/payments", headers=auth_for(finished_parent)).json()
    assert after["owed_paise"] == 0
    shown = next(item for item in after["payments"] if item["id"] == str(charge))
    assert shown["status"] == "waived" and shown["waive_reason"] == "A family emergency."
    page = client.get(f"/parent/payments/{charge}", headers=auth_for(finished_parent)).json()
    assert page["status"] == "waived" and page["pay_by_upi"] is None
    told = to(mailbox, finished_parent["email"])
    assert [email.subject for email in told] == ["Pacifyco has waived a charge"]
    assert row(db_engine, "SELECT amount_paise FROM payments WHERE id = :p", p=charge)["amount_paise"] == 69_900

    again = post(client, reviewer, f"charges/{charge}/waive", reason="Again")
    assert again.status_code == 409 and again.json()["error"]["code"] == "not_owed"


def test_not_while_a_payment_is_being_checked_and_never_a_booking_payment(client, db_engine, reviewer, confirmed, paid):
    charge = a_charge(db_engine, confirmed, reference="987654321098")
    checking = post(client, reviewer, f"charges/{charge}/waive", reason="Goodwill")
    assert checking.status_code == 409 and checking.json()["error"]["code"] == "payment_being_checked"
    booking_payment = post(client, reviewer, f"charges/{paid}/waive", reason="Goodwill")
    assert booking_payment.status_code == 404


def test_a_waived_charge_cant_be_paid(client, db_engine, reviewer, confirmed, finished_parent):
    charge = a_charge(db_engine, confirmed)
    assert post(client, reviewer, f"charges/{charge}/waive", reason="Goodwill").status_code == 200
    paying = client.post(
        f"/parent/payments/{charge}/payment", json={"upi_reference": "123123123123"}, headers=auth_for(finished_parent)
    )
    assert paying.status_code == 409


# ---------- the booking page ----------


def test_the_booking_page_for_admins(client, db_engine, reviewer, confirmed, finished_parent):
    found = detail(client, reviewer, confirmed["id"])
    assert found["parent"]["id"] == str(finished_parent["id"]) and found["sitter"]["id"] == str(confirmed["sitter_id"])
    units = scalar(db_engine, "SELECT units FROM bookings WHERE id = :b", b=confirmed["id"])
    assert found["children"] and found["units"] == units
    assert [item["kind"] for item in found["payments"]] == ["booking"]
    assert found["payments"][0]["status"] == "confirmed" and found["can_add_pay"] is False
    assert "payment_confirmed" in [event["action"] for event in found["history"]]
    missing = client.get("/admin/bookings/00000000-0000-0000-0000-000000000000", headers=as_user(reviewer))
    assert missing.status_code == 404
