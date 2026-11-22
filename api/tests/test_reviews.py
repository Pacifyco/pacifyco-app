# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Reviews both ways and the low-rating flag (CLAUDE.md 6.11; phase 9; Reuben, 2026-11-22).

Once per author per booking, only after a booking where care happened (checked out, or closed by an admin
after she checked in), within 14 days of its end. Parents see a sitter's average, count and written
reviews; only admins see a sitter's review of a parent. A sitter is flagged when her last-10 average is
below 3.5 (from 5 reviews); she's told the reason and can respond before any decision.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from tests.test_admin_payments import confirm, paid, verify_children  # noqa: F401
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_cancellations import confirmed  # noqa: F401  (fixture)
from tests.test_checkin import _copy_booking
from tests.test_documents import admin, as_user, client, parent, row, rows, scalar, storage  # noqa: F401
from tests.test_incidents import ADMINS, admins_told  # noqa: F401  (fixture)
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_payments import booking  # noqa: F401  (fixture)
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, user  # noqa: F401  (fixture)
from tests.test_sitter_bookings import signed_in
from tests.test_verification import reviewer  # noqa: F401  (fixture)


def finish(db_engine, booking_id, *, ended_ago=timedelta(hours=1), status="completed", checked_in=True):
    """The booking, 2 hours long, ended `ended_ago`; checked in at the start and out at the end."""
    ends = datetime.now(UTC) - ended_ago
    starts = ends - timedelta(hours=2)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE bookings SET status = :st, starts_at = :s, ends_at = :e, checked_in_at = :ci,"
                " checked_out_at = :co WHERE id = :b"
            ),
            {
                "st": status,
                "s": starts,
                "e": ends,
                "ci": starts if checked_in else None,
                "co": ends if checked_in else None,
                "b": booking_id,
            },
        )


def review(client, who, booking_id, rating, body=None):
    """The parent's review (`who` is a signed-in user, or headers)."""
    headers = auth_for(who) if "id" in who else who
    return client.post(f"/parent/bookings/{booking_id}/review", json={"rating": rating, "body": body}, headers=headers)


def sitter_of(db_engine, booking_id):
    return signed_in(db_engine, scalar(db_engine, "SELECT sitter_id FROM bookings WHERE id = :b", b=booking_id))


def sitter_rating(db_engine, booking_id):
    return row(
        db_engine,
        "SELECT s.avg_rating, s.review_count FROM sitters s JOIN bookings b ON b.sitter_id = s.profile_id"
        " WHERE b.id = :b",
        b=booking_id,
    )


@pytest.fixture
def done(db_engine, confirmed):
    """The confirmed booking, checked out an hour ago."""
    finish(db_engine, confirmed["id"])
    return confirmed


# ---------- leaving one ----------


def test_both_review_once_and_her_average_updates(client, db_engine, done, finished_parent):
    left = review(client, finished_parent, done["id"], 4, "  Lovely with the kids.  ")
    assert left.status_code == 201, left.text
    mine = left.json()["review"]
    assert mine["mine"]["rating"] == 4 and mine["mine"]["body"] == "Lovely with the kids."
    assert mine["can_review"] is False and mine["open_until"] is None
    rating = sitter_rating(db_engine, done["id"])
    assert float(rating["avg_rating"]) == 4.0 and rating["review_count"] == 1

    again = review(client, finished_parent, done["id"], 5)
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_reviewed"

    sitter = sitter_of(db_engine, done["id"])
    hers = client.post(f"/sitter/bookings/{done['id']}/review", json={"rating": 2}, headers=auth_for(sitter))
    assert hers.status_code == 201, hers.text
    assert hers.json()["review"]["mine"]["rating"] == 2
    # Her review of the family doesn't touch her own average.
    assert sitter_rating(db_engine, done["id"])["review_count"] == 1
    actions = [r["action"] for r in rows(db_engine, "SELECT action FROM audit_log WHERE entity = 'review'")]
    assert actions.count("review_left") == 2


def test_the_booking_shows_whether_they_can_review_and_until_when(client, db_engine, done, finished_parent):
    state = client.get(f"/parent/bookings/{done['id']}", headers=auth_for(finished_parent)).json()["review"]
    assert state["mine"] is None and state["can_review"] is True
    ends = scalar(db_engine, "SELECT ends_at FROM bookings WHERE id = :b", b=done["id"])
    assert datetime.fromisoformat(state["open_until"]) == ends + timedelta(days=14)


@pytest.mark.parametrize(
    ("status", "checked_in", "allowed"),
    [
        ("completed", True, True),
        ("closed_by_admin", True, True),  # closed by hand after she checked in: care happened
        ("closed_by_admin", False, False),  # she never checked in
        ("confirmed", False, False),
        ("sitter_no_show", False, False),
        ("cancelled_parent", False, False),
    ],
)
def test_only_after_care_happened(client, db_engine, confirmed, finished_parent, status, checked_in, allowed):
    finish(db_engine, confirmed["id"], status=status, checked_in=checked_in)
    left = review(client, finished_parent, confirmed["id"], 5)
    if allowed:
        assert left.status_code == 201, left.text
    else:
        assert left.status_code == 409 and left.json()["error"]["code"] == "not_reviewable"


def test_closed_14_days_after_the_end(client, db_engine, confirmed, finished_parent):
    finish(db_engine, confirmed["id"], ended_ago=timedelta(days=14, minutes=1))
    late = review(client, finished_parent, confirmed["id"], 5)
    assert late.status_code == 409 and late.json()["error"]["code"] == "review_closed"
    finish(db_engine, confirmed["id"], ended_ago=timedelta(days=13, hours=23))
    assert review(client, finished_parent, confirmed["id"], 5).status_code == 201


def test_rating_from_1_to_5_and_a_short_review(client, done, finished_parent):
    for bad in (0, 6):
        assert review(client, finished_parent, done["id"], bad).status_code == 422
    assert review(client, finished_parent, done["id"], 5, "x" * 501).status_code == 422


def test_only_their_own_bookings(client, db_engine, done, finished_parent, make_profile):
    other_parent = make_profile("parent")
    assert review(client, as_user(other_parent), done["id"], 1).status_code == 404
    other_sitter = make_profile("sitter")
    response = client.post(f"/sitter/bookings/{done['id']}/review", json={"rating": 1}, headers=as_user(other_sitter))
    assert response.status_code == 404


# ---------- who sees what ----------


def test_parents_see_her_reviews_but_only_admins_see_hers_of_a_family(
    client, db_engine, reviewer, done, finished_parent
):
    review(client, finished_parent, done["id"], 5, "Wonderful")
    sitter = sitter_of(db_engine, done["id"])
    client.post(
        f"/sitter/bookings/{done['id']}/review", json={"rating": 3, "body": "Came home late"}, headers=auth_for(sitter)
    )

    profile = client.get(f"/parent/sitters/{done['sitter_id']}", headers=auth_for(finished_parent)).json()
    assert profile["avg_rating"] == 5.0 and profile["review_count"] == 1
    assert [(r["rating"], r["body"]) for r in profile["reviews"]] == [(5, "Wonderful")]
    name = scalar(db_engine, "SELECT full_name FROM profiles WHERE id = :i", i=finished_parent["id"])
    assert profile["reviews"][0]["author_first_name"] == name.split()[0]
    # The parent's booking shows their own review, never the sitter's of them.
    booking = client.get(f"/parent/bookings/{done['id']}", headers=auth_for(finished_parent)).text
    assert "Came home late" not in booking

    # She sees families' reviews of her.
    hers = client.get("/sitter/reviews", headers=auth_for(sitter)).json()
    assert hers["review_count"] == 1 and hers["reviews"][0]["body"] == "Wonderful" and hers["flag"] is None

    # Admins see both.
    family = client.get(f"/admin/parents/{finished_parent['id']}", headers=as_user(reviewer)).json()
    assert [(r["rating"], r["body"]) for r in family["reviews"]] == [(3, "Came home late")]
    about_her = client.get(f"/admin/sitters/{done['sitter_id']}", headers=as_user(reviewer)).json()
    assert about_her["review_count"] == 1 and about_her["reviews"][0]["body"] == "Wonderful"


# ---------- the low-rating flag ----------


def more_bookings(db_engine, booking_id, count):
    """`count` more finished bookings like this one, a day apart, each checked out."""
    made = []
    for day in range(1, count + 1):
        starts = datetime.now(UTC) - timedelta(days=day, hours=3)
        copy = _copy_booking(db_engine, booking_id, starts)
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE bookings SET status = 'completed', checked_in_at = starts_at,"
                    " checked_out_at = ends_at WHERE id = :b"
                ),
                {"b": copy},
            )
        made.append(copy)
    return made


def flags(db_engine):
    return rows(db_engine, "SELECT * FROM rating_flags ORDER BY created_at")


def test_flagged_from_5_reviews_when_the_last_10_average_is_below_3_5(
    client, db_engine, mailbox, admins_told, done, finished_parent
):
    bookings = [done["id"], *more_bookings(db_engine, done["id"], 5)]
    for booking_id in bookings[:4]:  # four 2-star reviews: not enough reviews yet
        assert review(client, finished_parent, booking_id, 2).status_code == 201
    assert flags(db_engine) == []
    assert review(client, finished_parent, bookings[4], 3).status_code == 201  # 5 reviews, average 2.2
    flagged = flags(db_engine)
    assert len(flagged) == 1 and float(flagged[0]["average"]) == 2.2 and flagged[0]["reviews_counted"] == 5
    assert flagged[0]["status"] == "open"
    alerts = [email for email in mailbox.sent if email.subject == "A sitter's ratings are low"]
    assert sorted(email.to for email in alerts) == sorted(ADMINS)

    # Still low: no second flag while this one is open.
    assert review(client, finished_parent, bookings[5], 1).status_code == 201
    assert len(flags(db_engine)) == 1


def test_only_the_last_10_count(client, db_engine, done, finished_parent):
    from sqlalchemy.orm import Session

    from app.services import reviews

    bookings = [done["id"], *more_bookings(db_engine, done["id"], 10)]
    # Oldest first: one 1-star review, then ten 4-star ones.
    for booking_id, rating in zip(bookings, [1] + [4] * 10, strict=True):
        assert review(client, finished_parent, booking_id, rating).status_code == 201
    # Flagged at the 5th review (1, 4, 4, 4, 4: 3.4), once.
    flagged = flags(db_engine)
    assert len(flagged) == 1 and float(flagged[0]["average"]) == 3.4 and flagged[0]["reviews_counted"] == 5
    # Her profile shows the all-time average; the flag looks at the last 10 only.
    rating = sitter_rating(db_engine, done["id"])
    assert float(rating["avg_rating"]) == 3.73 and rating["review_count"] == 11
    with Session(db_engine) as db:
        average, count = reviews.last_ten(db, done["sitter_id"])
    assert float(average) == 4.0 and count == 10


@pytest.fixture
def flagged(client, db_engine, done, finished_parent):
    for booking_id in [done["id"], *more_bookings(db_engine, done["id"], 4)]:
        assert review(client, finished_parent, booking_id, 1).status_code == 201
    return flags(db_engine)[0]["id"]


def test_told_the_reason_she_responds_and_an_admin_closes_it(
    client, db_engine, mailbox, admins_told, reviewer, done, flagged
):
    sitter = sitter_of(db_engine, done["id"])
    # Not shown to her until she's told.
    assert client.get("/sitter/reviews", headers=auth_for(sitter)).json()["flag"] is None
    early = client.post(f"/sitter/rating-flags/{flagged}/respond", json={"response": "Hi"}, headers=auth_for(sitter))
    assert early.status_code == 404

    listed = client.get("/admin/rating-flags", headers=as_user(reviewer)).json()
    assert [item["id"] for item in listed] == [str(flagged)] and listed[0]["average"] == 1.0
    assert (
        client.post(f"/admin/rating-flags/{flagged}/tell", json={"reason": " "}, headers=as_user(reviewer)).status_code
        == 422
    )
    told = client.post(
        f"/admin/rating-flags/{flagged}/tell",
        json={"reason": "Families said you were on your phone."},
        headers=as_user(reviewer),
    )
    assert told.status_code == 200, told.text
    assert told.json()["status"] == "told"
    email = next(e for e in mailbox.sent if e.subject == "Your ratings are being reviewed")
    assert "on your phone" in email.body

    shown = client.get("/sitter/reviews", headers=auth_for(sitter)).json()["flag"]
    assert shown["reason"] == "Families said you were on your phone." and shown["response"] is None
    answered = client.post(
        f"/sitter/rating-flags/{flagged}/respond",
        json={"response": "It was the parent calling me."},
        headers=auth_for(sitter),
    )
    assert answered.status_code == 200, answered.text
    assert answered.json()["flag"]["response"] == "It was the parent calling me."
    assert [e.to for e in mailbox.sent if e.subject == "A sitter has responded about her ratings"] == ADMINS
    twice = client.post(f"/sitter/rating-flags/{flagged}/respond", json={"response": "x"}, headers=auth_for(sitter))
    assert twice.status_code == 409 and twice.json()["error"]["code"] == "already_responded"

    closed = client.post(
        f"/admin/rating-flags/{flagged}/close", json={"note": "Spoke to her; keeping her."}, headers=as_user(reviewer)
    )
    assert closed.status_code == 200, closed.text
    assert client.get("/admin/rating-flags", headers=as_user(reviewer)).json() == []
    assert client.get("/sitter/reviews", headers=auth_for(sitter)).json()["flag"] is None
    flag = flags(db_engine)[0]
    assert flag["status"] == "closed" and flag["response"] == "It was the parent calling me."
    actions = {
        r["action"]
        for r in rows(
            db_engine, "SELECT action FROM audit_log WHERE entity = 'rating_flag' AND entity_id = :i", i=str(flagged)
        )
    }
    assert actions == {"rating_flagged", "rating_flag_told", "rating_flag_responded", "rating_flag_closed"}


def test_another_sitter_cant_respond(client, db_engine, reviewer, flagged, make_profile):
    client.post(f"/admin/rating-flags/{flagged}/tell", json={"reason": "Low"}, headers=as_user(reviewer))
    other = make_profile("sitter")
    response = client.post(f"/sitter/rating-flags/{flagged}/respond", json={"response": "x"}, headers=as_user(other))
    assert response.status_code == 404


def test_reviews_and_flags_are_kept(db_engine, done, client, finished_parent, flagged):
    """The API's role can't change or delete a review, or delete a flag."""
    with db_engine.connect() as conn:
        conn.execute(text("SET ROLE pacifyco_api"))
        for statement in (
            "UPDATE reviews SET rating = 5",
            "DELETE FROM reviews",
            "DELETE FROM rating_flags",
            "UPDATE rating_flags SET average = 3",
        ):
            with pytest.raises(Exception, match="permission denied"):
                with conn.begin_nested():
                    conn.execute(text(statement))
        conn.rollback()


def test_she_has_12_hours_to_respond_before_its_closed(client, db_engine, reviewer, done, flagged):
    sitter = sitter_of(db_engine, done["id"])
    told = client.post(f"/admin/rating-flags/{flagged}/tell", json={"reason": "Low"}, headers=as_user(reviewer))
    assert told.json()["can_close"] is False
    told_at = datetime.fromisoformat(told.json()["told_at"])
    assert datetime.fromisoformat(told.json()["respond_by"]) == told_at + timedelta(hours=12)
    shown = client.get("/sitter/reviews", headers=auth_for(sitter)).json()["flag"]
    assert datetime.fromisoformat(shown["respond_by"]) == told_at + timedelta(hours=12)

    early = client.post(f"/admin/rating-flags/{flagged}/close", json={"note": "Remove"}, headers=as_user(reviewer))
    assert early.status_code == 409 and early.json()["error"]["code"] == "waiting_for_response"

    with db_engine.begin() as conn:  # her 12 hours have passed with no response
        conn.execute(
            text("UPDATE rating_flags SET told_at = now() - interval '12 hours 1 minute' WHERE id = :f"), {"f": flagged}
        )
    assert client.get("/admin/rating-flags", headers=as_user(reviewer)).json()[0]["can_close"] is True
    late = client.post(f"/admin/rating-flags/{flagged}/close", json={"note": "No reply"}, headers=as_user(reviewer))
    assert late.status_code == 200, late.text


def test_a_flag_she_was_never_told_about_can_be_closed_at_once(client, reviewer, flagged):
    listed = client.get("/admin/rating-flags", headers=as_user(reviewer)).json()[0]
    assert listed["can_close"] is True and listed["respond_by"] is None
    closed = client.post(
        f"/admin/rating-flags/{flagged}/close", json={"note": "Unfair reviews"}, headers=as_user(reviewer)
    )
    assert closed.status_code == 200, closed.text
