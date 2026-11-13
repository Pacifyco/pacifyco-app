"""The marketplace (CLAUDE.md 9 "Search and filters", phase 5): sitters' weekly hours and days off,
geocoding with a cache, and search. Only live sitters of the chosen plan's level are returned; each filter works;
distance sort; parents never see a sitter's pay."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import availability, geocoding
from app.services.geocoding import distance_km
from tests.test_checklists import CONTACTS
from tests.test_documents import (  # noqa: F401  (fixtures)
    accept_consent,
    add_child,
    cleanup_documents,
    client,
    parent,
    request_upload,
    row,
    rows,
    scalar,
    sitter,
    storage,
)
from tests.test_sign_up import DETAILS, PARENT, auth_for, fill_details, user  # noqa: F401  (fixture)
from tests.test_verification import upload


def india_day(days_from_today: int) -> date:
    return availability.today_in_india(datetime.now(UTC)) + timedelta(days=days_from_today)


def at(day: date, hour: int) -> datetime:
    """This India day and hour, as an aware datetime."""
    return datetime.combine(day, time(hour), availability.INDIA)


def set_week(client, who, *hours: tuple[int, int, int]):  # noqa: F811
    body = {"hours": [{"weekday": d, "start_hour": s, "end_hour": e} for d, s, e in hours]}
    return client.put("/sitter/availability/week", json=body, headers=auth_for(who))


@pytest.fixture
def finished_parent(client, db_engine, storage, parent):  # noqa: F811
    """A parent at 560034 who has finished their profile, so they can browse (CLAUDE.md 7)."""
    assert fill_details(client, parent).status_code == 200
    accept_consent(client, parent)
    child_id = add_child(db_engine, parent["id"])
    upload(client, storage, parent, "birth_certificate", child_id)
    put = client.put("/parent/emergency-contacts", json={"contacts": CONTACTS}, headers=auth_for(parent))
    assert put.status_code == 200
    return parent


@pytest.fixture
def make_sitter(client, db_engine):  # noqa: F811
    """Sitters with chosen details; live (approved, active, level set) unless told otherwise."""
    made = []

    def make(name="Lakshmi Nair", pin_code="560034", level="pause", live=True, **sitter_fields):
        identity = {"id": uuid.uuid4(), "email": f"sitter-{uuid.uuid4()}@example.com"}
        made.append(identity["id"])
        body = {**PARENT, "role": "sitter"}
        assert client.post("/me/profile", json=body, headers=auth_for(identity)).status_code == 201
        assert fill_details(client, identity, full_name=name, pin_code=pin_code).status_code == 200
        fields = {"years_experience": 2, "languages": ["English"], "first_aid": False, **sitter_fields}
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE sitters SET level = :level, onboarding_status = :onboarding, bio = 'Loves stories',"
                    " years_experience = :years_experience, languages = :languages, first_aid = :first_aid,"
                    " avg_rating = :avg_rating, review_count = :review_count WHERE profile_id = :id"
                ),
                {
                    "id": identity["id"],
                    "level": level,
                    "onboarding": "approved" if live else "in_progress",
                    "avg_rating": fields.get("avg_rating"),
                    "review_count": fields.get("review_count", 0),
                    **{k: fields[k] for k in ("years_experience", "languages", "first_aid")},
                },
            )
            status = "active" if live else "pending"
            conn.execute(text("UPDATE profiles SET status = :s WHERE id = :id"), {"s": status, "id": identity["id"]})
        return identity

    yield make
    for sitter_id in made:
        cleanup_documents(db_engine, sitter_id)


def find(client, who, **params):  # noqa: F811
    response = client.get("/parent/sitters", params={"plan": "pause", **params}, headers=auth_for(who))
    assert response.status_code == 200, response.text
    return response.json()


def names(results) -> list[str]:
    return [item["full_name"] for item in results]


# ---------- geocoding ----------


def test_saving_details_finds_the_home_on_the_map(client, db_engine, user, fake_geocoder):  # noqa: F811
    assert client.post("/me/profile", json=PARENT, headers=auth_for(user)).status_code == 201
    assert fill_details(client, user).status_code == 200
    position = row(db_engine, "SELECT lat, lng FROM profiles WHERE id = :id", id=user["id"])
    assert (position["lat"], position["lng"]) == (Decimal("12.935200"), Decimal("77.624500"))
    asked = len(fake_geocoder.queries)

    # Same address again: no new lookup.
    assert fill_details(client, user, full_name="Meera R").status_code == 200
    assert len(fake_geocoder.queries) == asked


def test_lookups_are_cached(client, db_engine, user, fake_geocoder):  # noqa: F811
    assert client.post("/me/profile", json=PARENT, headers=auth_for(user)).status_code == 201
    address = f"{uuid.uuid4()} Road"
    assert fill_details(client, user, address=address).status_code == 200
    assert len(fake_geocoder.queries) == 1
    cached = scalar(db_engine, "SELECT count(*) FROM geocode_cache WHERE query LIKE :q", q=f"{address.lower()}%")
    assert cached == 1

    other = {"id": uuid.uuid4(), "email": f"{uuid.uuid4()}@example.com"}
    try:
        assert client.post("/me/profile", json=PARENT, headers=auth_for(other)).status_code == 201
        assert fill_details(client, other, address=address).status_code == 200
        assert len(fake_geocoder.queries) == 1  # answered from the cache
    finally:
        cleanup_documents(db_engine, other["id"])


def test_a_failed_lookup_still_saves_the_details(client, db_engine, user, monkeypatch):  # noqa: F811
    monkeypatch.setattr(geocoding.NominatimGeocoder, "lookup", lambda self, query: None)
    with db_engine.begin() as conn:  # nothing cached either
        conn.execute(text("DELETE FROM geocode_cache"))
    assert client.post("/me/profile", json=PARENT, headers=auth_for(user)).status_code == 201
    response = fill_details(client, user, address=f"{uuid.uuid4()} Lane")
    assert response.status_code == 200
    assert response.json()["profile"]["details_complete"] is True
    assert row(db_engine, "SELECT lat FROM profiles WHERE id = :id", id=user["id"])["lat"] is None


def test_distance_between_two_points():
    koramangala = (Decimal("12.935200"), Decimal("77.624500"))
    kalyan_nagar = (Decimal("13.012500"), Decimal("77.627700"))
    assert distance_km(koramangala, kalyan_nagar) == pytest.approx(8.6, abs=0.1)
    assert distance_km(koramangala, (None, None)) is None


# ---------- availability ----------


def test_a_sitter_sets_her_week_and_it_replaces_the_old_one(client, sitter):  # noqa: F811
    response = set_week(client, sitter, (2, 18, 22), (0, 9, 13), (0, 13, 17))
    assert response.status_code == 200, response.text
    week = [(item["weekday"], item["start_hour"], item["end_hour"]) for item in response.json()["week"]]
    assert week == [(0, 9, 13), (0, 13, 17), (2, 18, 22)]  # sorted; touching times are fine

    assert set_week(client, sitter, (5, 18, 24)).status_code == 200
    listed = client.get("/sitter/availability", headers=auth_for(sitter)).json()
    assert listed["week"] == [{"weekday": 5, "start_hour": 18, "end_hour": 24}]
    assert set_week(client, sitter).json()["week"] == []  # not free at all


@pytest.mark.parametrize(
    ("hours", "code"),
    [
        ([(0, 9, 13), (0, 12, 15)], "hours_overlap"),
        ([(0, 13, 9)], "hours_order"),
        ([(0, 9, 9)], "hours_order"),
        ([(7, 9, 13)], "validation_error"),
        ([(0, 9, 25)], "validation_error"),
    ],
)
def test_bad_weeks_are_refused(client, sitter, hours, code):  # noqa: F811
    response = set_week(client, sitter, *hours)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code


def test_days_off_are_added_listed_and_removed(client, sitter):  # noqa: F811
    soon, later = india_day(3), india_day(10)
    for day in (later, soon, soon):  # the same day twice is fine
        response = client.post("/sitter/availability/days-off", json={"day": day.isoformat()}, headers=auth_for(sitter))
        assert response.status_code == 201
    assert response.json()["days_off"] == [soon.isoformat(), later.isoformat()]

    assert client.delete(f"/sitter/availability/days-off/{soon}", headers=auth_for(sitter)).status_code == 204
    assert client.get("/sitter/availability", headers=auth_for(sitter)).json()["days_off"] == [later.isoformat()]
    assert client.delete(f"/sitter/availability/days-off/{soon}", headers=auth_for(sitter)).status_code == 404


def test_a_day_off_in_the_past_is_refused(client, sitter):  # noqa: F811
    response = client.post(
        "/sitter/availability/days-off", json={"day": india_day(-1).isoformat()}, headers=auth_for(sitter)
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "day_in_the_past"


def test_a_sitter_cannot_remove_another_sitters_day_off(client, db_engine, sitter, make_sitter):  # noqa: F811
    other = make_sitter()
    day = india_day(4)
    client.post("/sitter/availability/days-off", json={"day": day.isoformat()}, headers=auth_for(other))
    assert client.delete(f"/sitter/availability/days-off/{day}", headers=auth_for(sitter)).status_code == 404
    assert scalar(db_engine, "SELECT count(*) FROM days_off WHERE sitter_id = :id", id=other["id"]) == 1


def test_parents_cannot_set_a_week(client, parent):  # noqa: F811
    assert set_week(client, parent, (0, 9, 13)).status_code == 403


def test_free_times_come_from_her_week_for_two_weeks(client, db_engine, make_sitter):  # noqa: F811
    found = make_sitter()
    # Mondays 9 am-1 pm, and Sunday evening running into Monday: 6 pm-midnight then midnight-2 am.
    set_week(client, found, (0, 9, 13), (6, 18, 24), (0, 0, 2))
    monday = date(2026, 11, 16)
    now = at(monday, 10)  # Monday 10 am in India: the morning has started but has time left
    with db_engine.begin() as conn:
        conn.execute(text("INSERT INTO days_off (sitter_id, day) VALUES (:id, '2026-11-23')"), {"id": found["id"]})

    with Session(db_engine) as db:
        times = availability.free_times(db, found["id"], now)
    spans = [(item.starts_at, item.ends_at) for item in times]
    sunday, next_monday = date(2026, 11, 22), date(2026, 11, 23)
    assert spans == [
        (at(monday, 9), at(monday, 13)),  # started, but kept: time is left
        (at(sunday, 18), at(next_monday, 0)),  # the 23rd is a day off, so no 0-2 am or 9-1 on it
        # 14 days from 16 Nov ends on 29 Nov (a Sunday): its evening is in, Monday the 30th is not.
        (at(date(2026, 11, 29), 18), at(date(2026, 11, 30), 0)),
    ]
    assert availability.is_free(times, at(monday, 10), at(monday, 12))
    assert not availability.is_free(times, at(monday, 12), at(monday, 14))
    assert availability.has_time_on(times, sunday, now)
    assert not availability.has_time_on(times, date(2026, 11, 18), now)


def test_times_that_touch_are_joined(client, db_engine, make_sitter):  # noqa: F811
    found = make_sitter()
    set_week(client, found, (6, 18, 24), (0, 0, 2))
    sunday = date(2026, 11, 15)
    with Session(db_engine) as db:
        times = availability.free_times(db, found["id"], at(sunday, 8))
    assert (times[0].starts_at, times[0].ends_at) == (at(sunday, 18), at(date(2026, 11, 16), 2))
    assert availability.is_free(times, at(sunday, 23), at(date(2026, 11, 16), 1))


# ---------- search ----------


def test_only_live_sitters_of_the_plans_level_are_found(client, db_engine, finished_parent, make_sitter):  # noqa: F811
    make_sitter("Live Pause")
    make_sitter("Live Unwind", level="unwind")
    make_sitter("Not Approved", live=False)
    suspended = make_sitter("Suspended Pause")
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE profiles SET status = 'suspended' WHERE id = :id"), {"id": suspended["id"]})

    assert names(find(client, finished_parent)) == ["Live Pause"]
    assert names(find(client, finished_parent, plan="unwind")) == ["Live Unwind"]


def test_parents_browse_only_once_their_profile_is_finished(client, parent):  # noqa: F811
    response = client.get("/parent/sitters", params={"plan": "pause"}, headers=auth_for(parent))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "profile_unfinished"


def test_sitters_cannot_search(client, sitter):  # noqa: F811
    assert client.get("/parent/sitters", params={"plan": "pause"}, headers=auth_for(sitter)).status_code == 403


def test_nearest_first(client, finished_parent, make_sitter):  # noqa: F811
    make_sitter("Far Away", pin_code="560084")
    make_sitter("Next Door", pin_code="560034")
    results = find(client, finished_parent)
    assert names(results) == ["Next Door", "Far Away"]
    assert results[0]["distance_km"] == 0.0
    assert results[1]["distance_km"] == pytest.approx(8.6, abs=0.1)


def test_sort_by_rating_and_experience(client, finished_parent, make_sitter):  # noqa: F811
    make_sitter("New", years_experience=1)
    make_sitter("Rated Four", years_experience=3, avg_rating=4.0, review_count=5)
    make_sitter("Rated Five", years_experience=6, avg_rating=5.0, review_count=2)
    assert names(find(client, finished_parent, sort="rating")) == ["Rated Five", "Rated Four", "New"]
    assert names(find(client, finished_parent, sort="experience")) == ["Rated Five", "Rated Four", "New"]


def test_several_languages_find_sitters_who_speak_any_of_them(client, finished_parent, make_sitter):  # noqa: F811
    # The language filter takes several (Reuben, 2026-11-13).
    make_sitter("Kannada Speaker", languages=["English", "Kannada"])
    make_sitter("Tamil Speaker", languages=["Tamil"])
    make_sitter("Hindi Speaker", languages=["Hindi"])
    found = find(client, finished_parent, language=["Kannada", "Tamil"])
    assert sorted(names(found)) == ["Kannada Speaker", "Tamil Speaker"]


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"language": "kannada"}, ["Kannada Speaker"]),
        ({"min_years": 5}, ["Experienced"]),
        ({"first_aid": "true"}, ["First Aider"]),
        ({"min_rating": 4.5}, ["Top Rated"]),
    ],
)
def test_each_filter_works(client, finished_parent, make_sitter, params, expected):  # noqa: F811
    make_sitter("Kannada Speaker", languages=["English", "Kannada"])
    make_sitter("Experienced", years_experience=8)
    make_sitter("First Aider", first_aid=True)
    make_sitter("Top Rated", avg_rating=4.8, review_count=3)
    make_sitter("Plain")
    assert names(find(client, finished_parent, **params)) == expected


def test_time_filter_needs_her_free_for_the_whole_time(client, finished_parent, make_sitter):  # noqa: F811
    day = india_day(3)
    free = make_sitter("Free All Morning")
    partly = make_sitter("Free Until Ten")
    set_week(client, free, (day.weekday(), 8, 12))
    set_week(client, partly, (day.weekday(), 8, 10))
    wanted = {"starts_at": at(day, 9).isoformat(), "ends_at": at(day, 11).isoformat()}
    assert names(find(client, finished_parent, **wanted)) == ["Free All Morning"]


def test_without_a_plan_every_live_sitter_is_found(client, db_engine, finished_parent, make_sitter):  # noqa: F811
    # Decided 2026-11-09: the parent's page lists every live sitter, whatever her level.
    make_sitter("Every Pause")
    make_sitter("Every Unwind", level="unwind")
    make_sitter("Every Recharge", level="recharge")
    make_sitter("Every Not Live", live=False)
    response = client.get("/parent/sitters", headers=auth_for(finished_parent))
    assert response.status_code == 200, response.text
    found = response.json()
    assert sorted(names(found)) == ["Every Pause", "Every Recharge", "Every Unwind"]
    # Each says which plan she works, so parents can tell them apart (a label, never a price).
    assert {item["full_name"]: item["plan"] for item in found} == {
        "Every Pause": "pause",
        "Every Unwind": "unwind",
        "Every Recharge": "recharge",
    }


def test_day_filter_finds_sitters_free_that_day(client, finished_parent, make_sitter):  # noqa: F811
    day = india_day(3)
    that_day = make_sitter("Free That Weekday")
    other_day = make_sitter("Free Another Weekday")
    off = make_sitter("Day Off That Day")
    make_sitter("Never Free")
    set_week(client, that_day, (day.weekday(), 9, 13))
    set_week(client, other_day, ((day.weekday() + 1) % 7, 9, 13))
    set_week(client, off, (day.weekday(), 9, 13))
    client.post("/sitter/availability/days-off", json={"day": day.isoformat()}, headers=auth_for(off))
    response = client.get("/parent/sitters", params={"day": day.isoformat()}, headers=auth_for(finished_parent))
    assert response.status_code == 200, response.text
    assert names(response.json()) == ["Free That Weekday"]


def test_time_of_day_filter_finds_sitters_free_then(client, finished_parent, make_sitter):  # noqa: F811
    # One set of parts of the day everywhere (UX review 2026-11-13): evening is 6 pm to 10 pm.
    day = india_day(3)
    evening = make_sitter("Free Evenings")
    late = make_sitter("Free From Nine")
    morning = make_sitter("Free Mornings")
    set_week(client, evening, (day.weekday(), 18, 22))
    set_week(client, late, (day.weekday(), 21, 24))
    set_week(client, morning, (day.weekday(), 9, 13))
    found = find(client, finished_parent, day=day.isoformat(), part="evening")
    assert sorted(names(found)) == ["Free Evenings", "Free From Nine"]
    assert names(find(client, finished_parent, day=day.isoformat(), part="morning")) == ["Free Mornings"]


def test_a_time_of_day_needs_a_day(client, finished_parent):  # noqa: F811
    response = client.get("/parent/sitters", params={"part": "evening"}, headers=auth_for(finished_parent))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "day_needed"


def test_nobody_is_free_beyond_two_weeks(client, finished_parent, make_sitter):  # noqa: F811
    make_sitter("Every Day")
    every_day = make_sitter("Every Day Too")
    set_week(client, every_day, *[(weekday, 9, 13) for weekday in range(7)])
    assert names(find(client, finished_parent, day=india_day(13).isoformat())) == ["Every Day Too"]
    assert names(find(client, finished_parent, day=india_day(14).isoformat())) == []


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"day": "tomorrow"}, "validation_error"),
        ({"starts_at": at(india_day(2), 9).isoformat()}, "time_incomplete"),
        ({"starts_at": at(india_day(2), 9).isoformat(), "ends_at": at(india_day(2), 8).isoformat()}, "time_order"),
        ({"plan": "deluxe"}, "validation_error"),
    ],
)
def test_bad_search_is_refused(client, finished_parent, params, code):  # noqa: F811
    response = client.get("/parent/sitters", params={"plan": "pause", **params}, headers=auth_for(finished_parent))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code


def test_parents_never_see_pay_or_contact_details(client, finished_parent, make_sitter):  # noqa: F811
    found = make_sitter("Lakshmi Nair")
    [summary] = find(client, finished_parent)
    detail = client.get(f"/parent/sitters/{found['id']}", headers=auth_for(finished_parent)).json()
    for shown in (summary, detail):
        text_shown = str(shown).lower()
        for hidden in ("pay", "rate", "address", "phone", "email", "upi", "bank", "health", "lat", "lng"):
            assert not any(hidden in key for key in shown), hidden
        assert DETAILS["phone"].replace(" ", "")[-10:] not in text_shown


# ---------- a sitter's profile page ----------


def test_profile_page_shows_her_week_and_days_off(client, finished_parent, make_sitter):  # noqa: F811
    found = make_sitter("Lakshmi Nair", languages=["English", "Tamil"])
    set_week(client, found, (0, 9, 13), (5, 18, 22))
    soon, beyond = india_day(2), india_day(20)
    for day in (soon, beyond):
        client.post("/sitter/availability/days-off", json={"day": day.isoformat()}, headers=auth_for(found))
    response = client.get(f"/parent/sitters/{found['id']}", headers=auth_for(finished_parent))
    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Lakshmi Nair"
    assert body["bio"] == "Loves stories"
    assert body["plan"] == "pause"
    assert body["languages"] == ["English", "Tamil"]
    assert body["joined_at"]  # "Joined Nov 2026" on her profile
    assert body["week"] == [
        {"weekday": 0, "start_hour": 9, "end_hour": 13},
        {"weekday": 5, "start_hour": 18, "end_hour": 22},
    ]
    assert body["days_off"] == [soon.isoformat()]  # only those within the next two weeks


def test_a_sitter_who_isnt_live_has_no_profile_page(client, finished_parent, make_sitter):  # noqa: F811
    hidden = make_sitter(live=False)
    response = client.get(f"/parent/sitters/{hidden['id']}", headers=auth_for(finished_parent))
    assert response.status_code == 404
    assert client.get(f"/parent/sitters/{uuid.uuid4()}", headers=auth_for(finished_parent)).status_code == 404


# ---------- Recharge sitters' reference (CLAUDE.md 6.2) ----------


def add_reference(db_engine, sitter_id, name="Asha Rao", outcome="approved"):
    with db_engine.begin() as conn:
        conn.execute(
            text(
                'INSERT INTO "references" (sitter_id, name, phone, relationship, outcome)'
                " VALUES (:s, :n, '+919876500000', 'Former employer', :o)"
            ),
            {"s": sitter_id, "n": name, "o": outcome},
        )


def set_consent(db_engine, sitter_id, consent=True):
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE sitters SET reference_shared_consent = :c WHERE profile_id = :id"),
            {"c": consent, "id": sitter_id},
        )


def detail(client, parent_user, sitter_user):  # noqa: F811
    return client.get(f"/parent/sitters/{sitter_user['id']}", headers=auth_for(parent_user)).json()


def test_a_recharge_sitters_reference_is_shown_with_her_consent(client, db_engine, finished_parent, make_sitter):  # noqa: F811
    recharge = make_sitter(level="recharge")
    add_reference(db_engine, recharge["id"], "Zara Pending", outcome="pending")
    add_reference(db_engine, recharge["id"], "Asha Rao")
    assert detail(client, finished_parent, recharge)["reference"] is None  # no consent yet

    set_consent(db_engine, recharge["id"])
    assert detail(client, finished_parent, recharge)["reference"] == {
        "name": "Asha Rao",  # only an approved reference, and never the referee's phone (UX review)
        "relationship": "Former employer",
    }


def test_other_levels_never_show_a_reference(client, db_engine, finished_parent, make_sitter):  # noqa: F811
    unwind = make_sitter(level="unwind")
    add_reference(db_engine, unwind["id"])
    set_consent(db_engine, unwind["id"])
    assert detail(client, finished_parent, unwind)["reference"] is None


def test_the_search_list_never_shows_references(client, db_engine, finished_parent, make_sitter):  # noqa: F811
    recharge = make_sitter(level="recharge")
    add_reference(db_engine, recharge["id"])
    set_consent(db_engine, recharge["id"])
    [summary] = find(client, finished_parent, plan="recharge")
    assert "reference" not in summary


def test_references_checked_only_with_an_approved_reference(client, db_engine, finished_parent, make_sitter):  # noqa: F811
    # References are optional (Reuben, 2026-11-13), so parents see "References checked" only when true.
    found = make_sitter("No Reference")
    assert detail(client, finished_parent, found)["references_checked"] is False
    add_reference(db_engine, found["id"], outcome="pending")
    assert detail(client, finished_parent, found)["references_checked"] is False
    add_reference(db_engine, found["id"], name="Ravi Kumar")
    assert detail(client, finished_parent, found)["references_checked"] is True
