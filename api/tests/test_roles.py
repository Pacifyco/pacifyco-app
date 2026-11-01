"""Role gates (CLAUDE.md 9): wrong role gets 403 on every role-gated endpoint; suspended and removed users
are blocked; every endpoint is either public on purpose or behind a role."""

import uuid
from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import get_key_source, require_role
from app.main import create_app
from app.models import Profile, Role
from app.settings import Settings
from tests.test_auth import FakeKeys, bearer, client, make_settings, token  # noqa: F401  (client is a fixture)

AREAS = {"/parent": Role.parent, "/sitter": Role.sitter, "/admin": Role.admin}

# Endpoints anyone may call (each checks what it needs itself). A new endpoint must either be added here
# on purpose or live in a role-gated router.
PUBLIC = {
    "/health",
    "/health/db",
    "/service-area",
    "/me",  # signed in, no profile needed
    "/me/profile",  # signed in, no profile needed (sign-up)
    "/internal/jobs/{run}",  # JOBS_SECRET
}


@pytest.fixture
def make_profile(db_engine):
    created = []

    def make(role: str, status: str = "pending") -> uuid.UUID:
        user_id = uuid.uuid4()
        with db_engine.begin() as conn:
            conn.execute(
                text("INSERT INTO profiles (id, role, full_name, email, status) VALUES (:id, :r, 'T', :e, :s)"),
                {"id": user_id, "r": role, "e": f"{user_id}@example.com", "s": status},
            )
        created.append(user_id)
        return user_id

    yield make
    with db_engine.begin() as conn:  # as the owner: acceptances are append-only for the API
        for user_id in created:
            conn.execute(text("DELETE FROM legal_acceptances WHERE profile_id = :id"), {"id": user_id})
            conn.execute(text("DELETE FROM profiles WHERE id = :id"), {"id": user_id})


def as_user(user_id: uuid.UUID) -> dict[str, str]:
    return bearer(token(sub=str(user_id)))


@pytest.fixture
def gated_client(db_engine):
    """The real app plus one test endpoint per area, using the same gate the area routers use."""
    from alembic import command

    from tests.test_migrations import alembic_config

    command.upgrade(alembic_config(db_engine), "head")
    app = create_app(make_settings(db_engine))
    app.dependency_overrides[get_key_source] = FakeKeys
    for prefix, role in AREAS.items():

        def whoami(profile: Annotated[Profile, Depends(require_role(role))]) -> dict[str, str]:
            return {"role": profile.role}

        app.add_api_route(f"{prefix}/_test", whoami, methods=["GET"])
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("area", AREAS)
@pytest.mark.parametrize("role", ["parent", "sitter", "admin"])
def test_each_area_lets_in_only_its_role(gated_client, make_profile, area, role):
    response = gated_client.get(f"{area}/_test", headers=as_user(make_profile(role)))
    if AREAS[area] == role:
        assert response.status_code == 200
        assert response.json() == {"role": role}
    else:
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"


def test_pending_accounts_can_use_their_area(gated_client, make_profile):
    assert gated_client.get("/parent/_test", headers=as_user(make_profile("parent", "pending"))).status_code == 200
    assert gated_client.get("/parent/_test", headers=as_user(make_profile("parent", "active"))).status_code == 200


@pytest.mark.parametrize("status", ["suspended", "removed"])
@pytest.mark.parametrize("role", ["parent", "sitter", "admin"])
def test_suspended_and_removed_accounts_are_blocked(gated_client, make_profile, status, role):
    area = next(prefix for prefix, area_role in AREAS.items() if area_role == role)
    response = gated_client.get(f"{area}/_test", headers=as_user(make_profile(role, status)))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_blocked"


def test_blocked_accounts_can_still_see_who_they_are(gated_client, make_profile):
    """So the web app can show the on-hold message."""
    response = gated_client.get("/me", headers=as_user(make_profile("sitter", "suspended")))
    assert response.status_code == 200
    assert response.json()["profile"]["status"] == "suspended"


def test_areas_need_a_profile_and_a_sign_in(gated_client):
    assert gated_client.get("/parent/_test").status_code == 401
    no_profile = gated_client.get("/parent/_test", headers=bearer(token()))
    assert no_profile.status_code == 403
    assert no_profile.json()["error"]["code"] == "profile_required"


def real_routes() -> list[APIRoute]:
    app = create_app(Settings(_env_file=None))
    return [route for route in app.routes if isinstance(route, APIRoute)]


def test_every_endpoint_is_public_on_purpose_or_role_gated():
    unexpected = [
        route.path
        for route in real_routes()
        if route.path not in PUBLIC and not any(route.path.startswith(prefix + "/") for prefix in AREAS)
    ]
    assert unexpected == [], "Add these to a role-gated router, or to PUBLIC in this test on purpose"


def test_every_area_endpoint_rejects_the_other_roles(client, make_profile):  # noqa: F811
    """Sweeps the real area routers, so each new parent/sitter/admin endpoint is covered automatically."""
    for route in real_routes():
        area = next((prefix for prefix in AREAS if route.path.startswith(prefix + "/")), None)
        if area is None:
            continue
        for role in {"parent", "sitter", "admin"} - {AREAS[area]}:
            for method in route.methods:
                path = route.path.replace("{", "").replace("}", "")  # any value; the gate runs first
                response = client.request(method, path, headers=as_user(make_profile(role)))
                assert response.status_code == 403, (method, route.path, role)
