"""Emergency contacts and authorised adults (CLAUDE.md 7 and 9, Family Terms 2.5): exactly two
emergency contacts per family, any number of authorised adults, no IDOR."""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app import cli
from tests.test_auth import client  # noqa: F401  (fixture)
from tests.test_roles import as_user, make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, user  # noqa: F401  (fixture)

CONTACT_A = {"name": "Priya Rao", "relationship": "Mother", "phone": "+91 98765 43210"}
CONTACT_B = {"name": "Vikram Rao", "relationship": "Father", "phone": "9876500000"}


@pytest.fixture
def parent(client, db_engine, user):  # noqa: F811
    assert client.post("/me/profile", json=PARENT, headers=auth_for(user)).status_code == 201
    yield user
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM emergency_contacts WHERE parent_id = :id"), {"id": user["id"]})
        conn.execute(text("DELETE FROM authorised_adults WHERE parent_id = :id"), {"id": user["id"]})
        for table, column in (("legal_acceptances", "profile_id"), ("consents", "parent_id")):
            conn.execute(text(f"DELETE FROM {table} WHERE {column} = :id"), {"id": user["id"]})
        conn.execute(text("DELETE FROM profiles WHERE id = :id"), {"id": user["id"]})


def rows(db_engine, sql: str, **params):
    with db_engine.connect() as conn:
        return conn.execute(text(sql), params).mappings().all()


# ---------- emergency contacts ----------


def test_no_contacts_yet(client, parent):  # noqa: F811
    assert client.get("/parent/emergency-contacts", headers=auth_for(parent)).json() == []


def test_setting_exactly_two_is_accepted(client, db_engine, parent):  # noqa: F811
    response = client.put(
        "/parent/emergency-contacts", json={"contacts": [CONTACT_A, CONTACT_B]}, headers=auth_for(parent)
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert {c["name"] for c in body} == {"Priya Rao", "Vikram Rao"}
    assert {c["phone"] for c in body} == {"+919876543210", "+919876500000"}
    assert len(rows(db_engine, "SELECT id FROM emergency_contacts WHERE parent_id = :id", id=parent["id"])) == 2


@pytest.mark.parametrize("contacts", [[], [CONTACT_A], [CONTACT_A, CONTACT_B, CONTACT_A]])
def test_anything_other_than_two_contacts_is_refused(client, contacts, parent):  # noqa: F811
    response = client.put("/parent/emergency-contacts", json={"contacts": contacts}, headers=auth_for(parent))
    assert response.status_code == 422


def test_an_invalid_phone_number_is_refused(client, parent):  # noqa: F811
    bad = {**CONTACT_B, "phone": "12345"}
    response = client.put("/parent/emergency-contacts", json={"contacts": [CONTACT_A, bad]}, headers=auth_for(parent))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_a_blank_name_is_refused(client, parent):  # noqa: F811
    bad = {**CONTACT_B, "name": "   "}
    response = client.put("/parent/emergency-contacts", json={"contacts": [CONTACT_A, bad]}, headers=auth_for(parent))
    assert response.status_code == 422


def test_replacing_removes_the_old_pair(client, db_engine, parent):  # noqa: F811
    client.put("/parent/emergency-contacts", json={"contacts": [CONTACT_A, CONTACT_B]}, headers=auth_for(parent))
    other_a = {"name": "Asha K", "relationship": "Aunt", "phone": "9000000001"}
    other_b = {"name": "Ravi K", "relationship": "Uncle", "phone": "9000000002"}
    response = client.put("/parent/emergency-contacts", json={"contacts": [other_a, other_b]}, headers=auth_for(parent))
    assert response.status_code == 200
    names = {c["name"] for c in response.json()}
    assert names == {"Asha K", "Ravi K"}
    all_rows = rows(db_engine, "SELECT name FROM emergency_contacts WHERE parent_id = :id", id=parent["id"])
    assert {row["name"] for row in all_rows} == {"Asha K", "Ravi K"}  # exactly two, old ones gone


def test_emergency_contacts_make_the_account_not_empty(client, db_engine, parent):  # noqa: F811
    client.put("/parent/emergency-contacts", json={"contacts": [CONTACT_A, CONTACT_B]}, headers=auth_for(parent))
    url = db_engine.url.render_as_string(hide_password=False)
    assert cli.delete_empty_profile(parent["email"], True, url) == 1


# ---------- authorised adults ----------


def test_no_authorised_adults_yet(client, parent):  # noqa: F811
    assert client.get("/parent/authorised-adults", headers=auth_for(parent)).json() == []


def test_adding_and_listing_an_authorised_adult(client, db_engine, parent):  # noqa: F811
    response = client.post("/parent/authorised-adults", json=CONTACT_A, headers=auth_for(parent))
    assert response.status_code == 201
    adult = response.json()
    assert adult["name"] == "Priya Rao"
    assert adult["phone"] == "+919876543210"
    listed = client.get("/parent/authorised-adults", headers=auth_for(parent)).json()
    assert [a["id"] for a in listed] == [adult["id"]]


def test_any_number_of_authorised_adults_is_allowed(client, parent):  # noqa: F811
    for n in range(3):
        contact = {"name": f"Adult {n}", "relationship": "Friend", "phone": "9876500000"}
        assert client.post("/parent/authorised-adults", json=contact, headers=auth_for(parent)).status_code == 201
    assert len(client.get("/parent/authorised-adults", headers=auth_for(parent)).json()) == 3


def test_removing_an_authorised_adult(client, parent):  # noqa: F811
    adult = client.post("/parent/authorised-adults", json=CONTACT_A, headers=auth_for(parent)).json()
    response = client.delete(f"/parent/authorised-adults/{adult['id']}", headers=auth_for(parent))
    assert response.status_code == 204
    assert client.get("/parent/authorised-adults", headers=auth_for(parent)).json() == []


def test_removing_an_adult_that_doesnt_exist_is_404(client, parent):  # noqa: F811
    response = client.delete(f"/parent/authorised-adults/{uuid.uuid4()}", headers=auth_for(parent))
    assert response.status_code == 404


def test_cannot_remove_someone_elses_authorised_adult(client, make_profile, parent):  # noqa: F811
    """No IDOR: changing the id in the URL doesn't let you touch another family's adult."""
    adult = client.post("/parent/authorised-adults", json=CONTACT_A, headers=auth_for(parent)).json()
    other_parent_id = make_profile("parent")
    response = client.delete(f"/parent/authorised-adults/{adult['id']}", headers=as_user(other_parent_id))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    # Still there: the other parent's attempt didn't remove it.
    assert len(client.get("/parent/authorised-adults", headers=auth_for(parent)).json()) == 1


def test_an_authorised_adult_makes_the_account_not_empty(client, db_engine, parent):  # noqa: F811
    client.post("/parent/authorised-adults", json=CONTACT_A, headers=auth_for(parent))
    url = db_engine.url.render_as_string(hide_password=False)
    assert cli.delete_empty_profile(parent["email"], True, url) == 1


# ---------- children ----------

CHILD = {"name": "Asha K", "date_of_birth": "2023-05-01", "allergies": "Peanuts"}


def test_no_children_yet(client, parent):  # noqa: F811
    assert client.get("/parent/children", headers=auth_for(parent)).json() == []


def test_adding_a_child(client, parent):  # noqa: F811
    response = client.post("/parent/children", json=CHILD, headers=auth_for(parent))
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Asha K"
    assert body["date_of_birth"] == "2023-05-01"
    assert body["allergies"] == "Peanuts"
    assert body["medical_notes"] is None
    assert body["verification_status"] == "pending"


def test_a_newborn_can_be_added_no_age_check_here(client, parent):  # noqa: F811
    """CLAUDE.md 6.4: the 18-month check happens at booking time, not when adding a child."""
    newborn = {**CHILD, "name": "Newborn", "date_of_birth": date.today().isoformat()}
    assert client.post("/parent/children", json=newborn, headers=auth_for(parent)).status_code == 201


def test_a_future_date_of_birth_is_refused(client, parent):  # noqa: F811
    bad = {**CHILD, "date_of_birth": (date.today() + timedelta(days=1)).isoformat()}
    response = client.post("/parent/children", json=bad, headers=auth_for(parent))
    assert response.status_code == 422


def test_a_blank_child_name_is_refused(client, parent):  # noqa: F811
    bad = {**CHILD, "name": "   "}
    response = client.post("/parent/children", json=bad, headers=auth_for(parent))
    assert response.status_code == 422


def test_listing_shows_added_children(client, parent):  # noqa: F811
    client.post("/parent/children", json=CHILD, headers=auth_for(parent))
    client.post("/parent/children", json={**CHILD, "name": "Rohan K"}, headers=auth_for(parent))
    listed = client.get("/parent/children", headers=auth_for(parent)).json()
    assert {c["name"] for c in listed} == {"Asha K", "Rohan K"}


def test_updating_a_child(client, parent):  # noqa: F811
    child = client.post("/parent/children", json=CHILD, headers=auth_for(parent)).json()
    update = {**CHILD, "name": "Asha Kumar", "medical_notes": "Mild asthma"}
    response = client.put(f"/parent/children/{child['id']}", json=update, headers=auth_for(parent))
    assert response.status_code == 200
    assert response.json()["name"] == "Asha Kumar"
    assert response.json()["medical_notes"] == "Mild asthma"


def test_removing_a_child(client, parent):  # noqa: F811
    child = client.post("/parent/children", json=CHILD, headers=auth_for(parent)).json()
    assert client.delete(f"/parent/children/{child['id']}", headers=auth_for(parent)).status_code == 204
    assert client.get("/parent/children", headers=auth_for(parent)).json() == []


def test_a_child_that_doesnt_exist_is_404(client, parent):  # noqa: F811
    response = client.put(f"/parent/children/{uuid.uuid4()}", json=CHILD, headers=auth_for(parent))
    assert response.status_code == 404


def test_cannot_touch_someone_elses_child(client, make_profile, parent):  # noqa: F811
    """No IDOR: changing the id in the URL doesn't let you touch another family's child."""
    child = client.post("/parent/children", json=CHILD, headers=auth_for(parent)).json()
    other_parent_id = make_profile("parent")
    response = client.delete(f"/parent/children/{child['id']}", headers=as_user(other_parent_id))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert len(client.get("/parent/children", headers=auth_for(parent)).json()) == 1


def test_a_child_makes_the_account_not_empty(client, db_engine, parent):  # noqa: F811
    client.post("/parent/children", json=CHILD, headers=auth_for(parent))
    url = db_engine.url.render_as_string(hide_password=False)
    assert cli.delete_empty_profile(parent["email"], True, url) == 1
