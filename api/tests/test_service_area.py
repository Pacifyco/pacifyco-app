"""Service area: a home pin code is only accepted in the launch pin codes (CLAUDE.md 1 and 9). It is
entered after sign-up with the rest of the details (6.13). Booking checks come with booking."""

from contextlib import contextmanager

import pytest
from sqlalchemy import text

from tests.test_auth import client  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, fill_details, row, user  # noqa: F401  (user is a fixture)

LAUNCH_PIN_CODES = ["560001", "560034", "560038", "560078", "560084", "560095", "560103"]


@contextmanager
def paused(db_engine, pin_code: str):
    """Switch a pin code off for one test."""
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE service_area_pincodes SET active = false WHERE pin_code = :p"), {"p": pin_code})
    try:
        yield
    finally:
        with db_engine.begin() as conn:
            conn.execute(text("UPDATE service_area_pincodes SET active = true WHERE pin_code = :p"), {"p": pin_code})


@pytest.fixture
def signed_up(client, user):  # noqa: F811
    assert client.post("/me/profile", json=PARENT, headers=auth_for(user)).status_code == 201
    return user


@pytest.mark.parametrize("pin_code", LAUNCH_PIN_CODES)
def test_every_launch_pin_code_is_accepted(client, db_engine, signed_up, pin_code):  # noqa: F811
    assert fill_details(client, signed_up, pin_code=pin_code).status_code == 200
    assert row(db_engine, "SELECT pin_code FROM profiles WHERE id = :id", signed_up["id"])["pin_code"] == pin_code


@pytest.mark.parametrize("role", ["parent", "sitter"])
@pytest.mark.parametrize("pin_code", ["560002", "560100", "110001", "000000"])
def test_a_pin_code_outside_the_service_area_is_refused(client, db_engine, user, role, pin_code):  # noqa: F811
    assert client.post("/me/profile", json={**PARENT, "role": role}, headers=auth_for(user)).status_code == 201
    response = fill_details(client, user, pin_code=pin_code)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "outside_service_area"
    assert row(db_engine, "SELECT pin_code FROM profiles WHERE id = :id", user["id"])["pin_code"] is None


def test_a_paused_pin_code_is_refused(client, db_engine, signed_up):  # noqa: F811
    with paused(db_engine, "560001"):
        response = fill_details(client, signed_up, pin_code="560001")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "outside_service_area"


def test_service_area_lists_active_pin_codes_without_sign_in(client, db_engine):  # noqa: F811
    response = client.get("/service-area")
    assert response.status_code == 200
    assert response.json() == {"pin_codes": LAUNCH_PIN_CODES}
    with paused(db_engine, "560078"):
        assert "560078" not in client.get("/service-area").json()["pin_codes"]
