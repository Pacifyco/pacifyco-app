"""Service area: sign-up only in the launch pin codes (CLAUDE.md 1 and 9). Booking checks come in phase 6."""

from contextlib import contextmanager

import pytest
from sqlalchemy import text

from tests.test_auth import client  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, row, user  # noqa: F401  (user is a fixture)

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


@pytest.mark.parametrize("pin_code", LAUNCH_PIN_CODES)
def test_every_launch_pin_code_can_sign_up(client, db_engine, user, pin_code):  # noqa: F811
    response = client.post("/me/profile", json={**PARENT, "pin_code": pin_code}, headers=auth_for(user))
    assert response.status_code == 201
    assert row(db_engine, "SELECT pin_code FROM profiles WHERE id = :id", user["id"])["pin_code"] == pin_code


@pytest.mark.parametrize("role", ["parent", "sitter"])
@pytest.mark.parametrize("pin_code", ["560002", "560100", "110001", "000000"])
def test_sign_up_outside_the_service_area_is_refused(client, db_engine, user, role, pin_code):  # noqa: F811
    body = {**PARENT, "role": role, "pin_code": pin_code}
    response = client.post("/me/profile", json=body, headers=auth_for(user))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "outside_service_area"
    assert row(db_engine, "SELECT 1 FROM profiles WHERE id = :id", user["id"]) is None


def test_a_paused_pin_code_is_refused(client, db_engine, user):  # noqa: F811
    with paused(db_engine, "560001"):
        response = client.post("/me/profile", json={**PARENT, "pin_code": "560001"}, headers=auth_for(user))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "outside_service_area"


def test_service_area_lists_active_pin_codes_without_sign_in(client, db_engine):  # noqa: F811
    response = client.get("/service-area")
    assert response.status_code == 200
    assert response.json() == {"pin_codes": LAUNCH_PIN_CODES}
    with paused(db_engine, "560078"):
        assert "560078" not in client.get("/service-area").json()["pin_codes"]
