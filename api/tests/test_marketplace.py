"""The marketplace (CLAUDE.md 9 "Search and filters", phase 5): sitters' free times, geocoding with a
cache, and search. Only live sitters of the chosen plan's level are returned; each filter works;
distance sort; parents never see a sitter's pay."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.services import geocoding, search
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


def _hour(days: int, hour: int) -> datetime:
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(days=days)
    return start.replace(hour=hour)


def slot(starts_at: datetime, hours: int = 3) -> dict[str, str]:
    return {"starts_at": starts_at.isoformat(), "ends_at": (starts_at + timedelta(hours=hours)).isoformat()}


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


def test_a_sitter_adds_lists_and_removes_free_times(client, sitter):  # noqa: F811
    later, sooner = _hour(3, 9), _hour(2, 9)
    for start in (later, sooner):
        response = client.post("/sitter/availability", json=slot(start), headers=auth_for(sitter))
        assert response.status_code == 201
    listed = client.get("/sitter/availability", headers=auth_for(sitter)).json()
    assert [datetime.fromisoformat(item["starts_at"]) for item in listed] == [sooner, later]

    deleted = client.delete(f"/sitter/availability/{listed[0]['id']}", headers=auth_for(sitter))
    assert deleted.status_code == 204
    assert len(client.get("/sitter/availability", headers=auth_for(sitter)).json()) == 1


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (slot(_hour(-1, 9)), "slot_in_the_past"),
        (
            {"starts_at": _hour(2, 9).isoformat(), "ends_at": (_hour(2, 9) + timedelta(minutes=30)).isoformat()},
            "slot_too_short",
        ),
        ({"starts_at": _hour(2, 9).isoformat(), "ends_at": _hour(2, 8).isoformat()}, "validation_error"),
        ({"starts_at": "2026-12-01T09:00:00", "ends_at": "2026-12-01T12:00:00"}, "validation_error"),  # no timezone
    ],
)
def test_bad_free_times_are_refused(client, sitter, body, code):  # noqa: F811
    response = client.post("/sitter/availability", json=body, headers=auth_for(sitter))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code


def test_free_times_cannot_overlap(client, sitter):  # noqa: F811
    assert client.post("/sitter/availability", json=slot(_hour(2, 9)), headers=auth_for(sitter)).status_code == 201
    response = client.post("/sitter/availability", json=slot(_hour(2, 11)), headers=auth_for(sitter))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "slot_overlaps"
    # Back to back is fine.
    assert client.post("/sitter/availability", json=slot(_hour(2, 12)), headers=auth_for(sitter)).status_code == 201


def test_a_sitter_cannot_remove_another_sitters_time(client, sitter, make_sitter):  # noqa: F811
    other = make_sitter()
    slot_id = client.post("/sitter/availability", json=slot(_hour(2, 9)), headers=auth_for(other)).json()["id"]
    assert client.delete(f"/sitter/availability/{slot_id}", headers=auth_for(sitter)).status_code == 403
    assert client.delete(f"/sitter/availability/{uuid.uuid4()}", headers=auth_for(sitter)).status_code == 404


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


def test_availability_filter_needs_her_free_for_the_whole_time(client, finished_parent, make_sitter):  # noqa: F811
    free = make_sitter("Free All Morning")
    partly = make_sitter("Free Until Ten")
    client.post("/sitter/availability", json=slot(_hour(2, 8), hours=4), headers=auth_for(free))
    client.post("/sitter/availability", json=slot(_hour(2, 8), hours=2), headers=auth_for(partly))
    wanted = {"starts_at": _hour(2, 9).isoformat(), "ends_at": _hour(2, 11).isoformat()}
    assert names(find(client, finished_parent, **wanted)) == ["Free All Morning"]


def test_without_a_plan_every_live_sitter_is_found(client, db_engine, finished_parent, make_sitter):  # noqa: F811
    # Decided 2026-11-09: the parent's page lists every live sitter, whatever her level.
    make_sitter("Every Pause")
    make_sitter("Every Unwind", level="unwind")
    make_sitter("Every Recharge", level="recharge")
    make_sitter("Every Not Live", live=False)
    response = client.get("/parent/sitters", headers=auth_for(finished_parent))
    assert response.status_code == 200, response.text
    assert sorted(names(response.json())) == ["Every Pause", "Every Recharge", "Every Unwind"]


def test_day_filter_finds_sitters_with_free_time_that_day(client, finished_parent, make_sitter):  # noqa: F811
    that_day = make_sitter("Free That Day")
    next_day = make_sitter("Free The Next Day")
    make_sitter("Never Free")
    # 6 am UTC is 11:30 am in India, so these free times sit inside one India day.
    client.post("/sitter/availability", json=slot(_hour(3, 6)), headers=auth_for(that_day))
    client.post("/sitter/availability", json=slot(_hour(4, 6)), headers=auth_for(next_day))
    day = _hour(3, 6).astimezone(search.INDIA).date().isoformat()
    response = client.get("/parent/sitters", params={"day": day}, headers=auth_for(finished_parent))
    assert response.status_code == 200, response.text
    assert names(response.json()) == ["Free That Day"]


def test_day_bounds_use_india_time_and_skip_the_past():
    day = date(2026, 12, 1)
    start, end = search.day_bounds(day, datetime(2026, 11, 1, tzinfo=UTC))
    assert start == datetime(2026, 11, 30, 18, 30, tzinfo=UTC)  # midnight in India
    assert end == datetime(2026, 12, 1, 18, 30, tzinfo=UTC)
    later = datetime(2026, 12, 1, 10, 0, tzinfo=UTC)
    assert search.day_bounds(day, later)[0] == later  # today: only what's left of it


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"day": "tomorrow"}, "validation_error"),
        ({"starts_at": _hour(2, 9).isoformat()}, "time_incomplete"),
        ({"starts_at": _hour(2, 9).isoformat(), "ends_at": _hour(2, 8).isoformat()}, "time_order"),
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


def test_profile_page_shows_her_free_times(client, finished_parent, make_sitter):  # noqa: F811
    found = make_sitter("Lakshmi Nair", languages=["English", "Tamil"])
    client.post("/sitter/availability", json=slot(_hour(2, 9)), headers=auth_for(found))
    response = client.get(f"/parent/sitters/{found['id']}", headers=auth_for(finished_parent))
    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Lakshmi Nair"
    assert body["bio"] == "Loves stories"
    assert body["plan"] == "pause"
    assert body["languages"] == ["English", "Tamil"]
    assert [datetime.fromisoformat(item["starts_at"]) for item in body["free_times"]] == [_hour(2, 9)]


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
        "name": "Asha Rao",  # only an approved reference
        "phone": "+919876500000",
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
