"""A sitter's own application and profile (CLAUDE.md sections 6.2, 7 and 9): 18+, no rate of her own,
health disclosure and bank details encrypted at rest and never shown to parents, exactly two
references, no IDOR."""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from tests.test_auth import client  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, user  # noqa: F401  (fixture)

PROFILE_BODY = {
    "date_of_birth": "1995-06-15",
    "bio": "I love looking after kids.",
    "years_experience": 5,
    "age_groups": ["toddler", "preschool"],
    "languages": ["English", "Kannada"],
    "first_aid": True,
}


def years_ago(years: int) -> str:
    return date.today().replace(year=date.today().year - years).isoformat()


@pytest.fixture
def sitter(client, db_engine, user):  # noqa: F811
    assert client.post("/me/profile", json={**PARENT, "role": "sitter"}, headers=auth_for(user)).status_code == 201
    yield user
    with db_engine.begin() as conn:
        conn.execute(text('DELETE FROM "references" WHERE sitter_id = :id'), {"id": user["id"]})
        for table, column in (("legal_acceptances", "profile_id"), ("consents", "parent_id")):
            conn.execute(text(f"DELETE FROM {table} WHERE {column} = :id"), {"id": user["id"]})
        conn.execute(text("DELETE FROM profiles WHERE id = :id"), {"id": user["id"]})


def row(db_engine, sql: str, **params):
    with db_engine.connect() as conn:
        return conn.execute(text(sql), params).mappings().first()


# ---------- profile ----------


def test_profile_starts_empty(client, sitter):  # noqa: F811
    response = client.get("/sitter/profile", headers=auth_for(sitter))
    assert response.status_code == 200
    body = response.json()
    assert body["date_of_birth"] is None
    assert body["onboarding_status"] == "in_progress"


def test_saving_a_profile(client, db_engine, sitter):  # noqa: F811
    response = client.put("/sitter/profile", json=PROFILE_BODY, headers=auth_for(sitter))
    assert response.status_code == 200
    body = response.json()
    assert body["date_of_birth"] == "1995-06-15"
    assert body["bio"] == "I love looking after kids."
    assert body["age_groups"] == ["toddler", "preschool"]

    stored = row(db_engine, "SELECT years_experience FROM sitters WHERE profile_id = :id", id=sitter["id"])
    assert stored["years_experience"] == 5


def test_sharing_a_reference_is_off_unless_she_ticks_it(client, db_engine, sitter):  # noqa: F811
    """CLAUDE.md 6.2: at Recharge level her reference is shown to parents only with her consent."""
    assert (
        client.put("/sitter/profile", json=PROFILE_BODY, headers=auth_for(sitter)).json()["reference_shared_consent"]
        is False
    )
    body = {**PROFILE_BODY, "reference_shared_consent": True}
    assert client.put("/sitter/profile", json=body, headers=auth_for(sitter)).json()["reference_shared_consent"] is True
    stored = row(db_engine, "SELECT reference_shared_consent FROM sitters WHERE profile_id = :id", id=sitter["id"])
    assert stored["reference_shared_consent"] is True


def test_sitter_under_18_rejected(client, sitter):  # noqa: F811
    body = {**PROFILE_BODY, "date_of_birth": years_ago(17)}
    response = client.put("/sitter/profile", json=body, headers=auth_for(sitter))
    assert response.status_code == 422


def test_birthday_in_the_future_rejected(client, sitter):  # noqa: F811
    future = (date.today() + timedelta(days=1)).isoformat()
    response = client.put("/sitter/profile", json={**PROFILE_BODY, "date_of_birth": future}, headers=auth_for(sitter))
    assert response.status_code == 422


def test_sitters_set_no_rate(client, sitter):  # noqa: F811
    # Pay is fixed by the sitter's level (CLAUDE.md 6.2): a rate sent by an old client is ignored.
    body = {**PROFILE_BODY, "hourly_rate_paise": 10_000}
    response = client.put("/sitter/profile", json=body, headers=auth_for(sitter))
    assert response.status_code == 200
    assert "hourly_rate_paise" not in response.json()


# ---------- health disclosure (encrypted, never shown to parents) ----------


def test_health_disclosure_round_trips_and_is_encrypted_at_rest(client, db_engine, sitter):  # noqa: F811
    assert client.get("/sitter/health-disclosure", headers=auth_for(sitter)).json() == {"disclosure": None}

    text_in = "Mild peanut allergy."
    response = client.put("/sitter/health-disclosure", json={"disclosure": text_in}, headers=auth_for(sitter))
    assert response.status_code == 200
    assert response.json() == {"disclosure": text_in}

    stored = row(db_engine, "SELECT health_disclosure_encrypted FROM sitters WHERE profile_id = :id", id=sitter["id"])
    assert text_in.encode() not in bytes(stored["health_disclosure_encrypted"])

    assert client.get("/sitter/health-disclosure", headers=auth_for(sitter)).json() == {"disclosure": text_in}

    # Clearing it stores null, not ciphertext of an empty string.
    client.put("/sitter/health-disclosure", json={"disclosure": None}, headers=auth_for(sitter))
    cleared = row(db_engine, "SELECT health_disclosure_encrypted FROM sitters WHERE profile_id = :id", id=sitter["id"])
    assert cleared["health_disclosure_encrypted"] is None


# ---------- payout details ----------


def test_payout_bank_requires_every_field(client, sitter):  # noqa: F811
    response = client.put(
        "/sitter/payout-details",
        json={"method": "bank", "account_holder_name": "Asha Rao"},
        headers=auth_for(sitter),
    )
    assert response.status_code == 422


def test_payout_bank_saves_and_encrypts(client, db_engine, sitter):  # noqa: F811
    body = {
        "method": "bank",
        "account_holder_name": "Asha Rao",
        "account_number": "123456789012",
        "ifsc_code": "HDFC0000123",
    }
    response = client.put("/sitter/payout-details", json=body, headers=auth_for(sitter))
    assert response.status_code == 200
    assert response.json() == {**body, "upi_id": None}

    stored = row(
        db_engine,
        "SELECT bank_details_encrypted, upi_id, payout_method FROM sitters WHERE profile_id = :id",
        id=sitter["id"],
    )
    assert stored["payout_method"] == "bank"
    assert stored["upi_id"] is None
    assert b"123456789012" not in bytes(stored["bank_details_encrypted"])

    get_response = client.get("/sitter/payout-details", headers=auth_for(sitter))
    assert get_response.json() == {**body, "upi_id": None}


@pytest.mark.parametrize("upi_id", ["not-a-upi-id", "", "a@"])
def test_payout_upi_rejects_bad_ids(client, sitter, upi_id):  # noqa: F811
    response = client.put("/sitter/payout-details", json={"method": "upi", "upi_id": upi_id}, headers=auth_for(sitter))
    assert response.status_code == 422


def test_payout_upi_saves_and_clears_bank_details(client, sitter):  # noqa: F811
    bank_body = {
        "method": "bank",
        "account_holder_name": "Asha Rao",
        "account_number": "123456789012",
        "ifsc_code": "HDFC0000123",
    }
    client.put("/sitter/payout-details", json=bank_body, headers=auth_for(sitter))

    response = client.put(
        "/sitter/payout-details", json={"method": "upi", "upi_id": "asha@upi"}, headers=auth_for(sitter)
    )
    expected = {
        "method": "upi",
        "upi_id": "asha@upi",
        "account_holder_name": None,
        "account_number": None,
        "ifsc_code": None,
    }
    assert response.status_code == 200
    assert response.json() == expected

    get_response = client.get("/sitter/payout-details", headers=auth_for(sitter))
    assert get_response.json() == expected


# ---------- references ----------


def test_no_references_yet(client, sitter):  # noqa: F811
    assert client.get("/sitter/references", headers=auth_for(sitter)).json() == []


def test_adding_two_references(client, sitter):  # noqa: F811
    first = client.post(
        "/sitter/references",
        json={"name": "Priya Rao", "relationship": "Neighbour", "phone": "9876543210"},
        headers=auth_for(sitter),
    )
    assert first.status_code == 201
    assert first.json()["outcome"] == "pending"

    second = client.post(
        "/sitter/references",
        json={"name": "Vikram Rao", "relationship": "Former employer", "phone": "9876500000"},
        headers=auth_for(sitter),
    )
    assert second.status_code == 201

    listed = client.get("/sitter/references", headers=auth_for(sitter)).json()
    assert {r["name"] for r in listed} == {"Priya Rao", "Vikram Rao"}


def test_a_third_reference_is_refused(client, sitter):  # noqa: F811
    for name in ("Priya Rao", "Vikram Rao"):
        client.post(
            "/sitter/references",
            json={"name": name, "relationship": "Neighbour", "phone": "9876543210"},
            headers=auth_for(sitter),
        )
    third = client.post(
        "/sitter/references",
        json={"name": "Meera", "relationship": "Friend", "phone": "9876500001"},
        headers=auth_for(sitter),
    )
    assert third.status_code == 409


def test_removing_a_reference(client, sitter):  # noqa: F811
    created = client.post(
        "/sitter/references",
        json={"name": "Priya Rao", "relationship": "Neighbour", "phone": "9876543210"},
        headers=auth_for(sitter),
    ).json()
    response = client.delete(f"/sitter/references/{created['id']}", headers=auth_for(sitter))
    assert response.status_code == 204
    assert client.get("/sitter/references", headers=auth_for(sitter)).json() == []


def test_cannot_remove_another_sitters_reference(client, db_engine, sitter):  # noqa: F811
    other_id = uuid.uuid4()
    other_user = {"id": other_id, "email": f"{other_id}@example.com"}
    try:
        with db_engine.begin() as conn:
            conn.execute(
                text("INSERT INTO profiles (id, role, full_name, email) VALUES (:id, 'sitter', 'Other', :e)"),
                {"id": other_user["id"], "e": other_user["email"]},
            )
            conn.execute(text("INSERT INTO sitters (profile_id) VALUES (:id)"), {"id": other_user["id"]})

        created = client.post(
            "/sitter/references",
            json={"name": "Priya Rao", "relationship": "Neighbour", "phone": "9876543210"},
            headers=auth_for(other_user),
        ).json()

        response = client.delete(f"/sitter/references/{created['id']}", headers=auth_for(sitter))
        assert response.status_code == 403
    finally:
        with db_engine.begin() as conn:
            conn.execute(text('DELETE FROM "references" WHERE sitter_id = :id'), {"id": other_user["id"]})
            conn.execute(text("DELETE FROM profiles WHERE id = :id"), {"id": other_user["id"]})
