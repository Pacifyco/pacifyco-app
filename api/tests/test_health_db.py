"""/health/db: proves the API can sign in to its database, and as which kind of role."""

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import API_ROLE
from app.main import create_app
from app.settings import Settings
from tests.test_migrations import alembic_config

TEST_PASSWORD = "test-only-password"


def client_for(database_url: str) -> TestClient:
    settings = Settings(
        _env_file=None, environment="staging", cors_origins="https://staging.example", database_url=database_url
    )
    return TestClient(create_app(settings), raise_server_exceptions=False)


@pytest.fixture
def api_role_url(db_engine):
    """Let pacifyco_api sign in to the test database for this test only."""
    command.upgrade(alembic_config(db_engine), "head")
    with db_engine.begin() as conn:
        conn.execute(text(f"ALTER ROLE {API_ROLE} WITH LOGIN PASSWORD '{TEST_PASSWORD}'"))
    url = db_engine.url.set(username=API_ROLE, password=TEST_PASSWORD).render_as_string(hide_password=False)
    yield url
    with db_engine.begin() as conn:
        conn.execute(text(f"ALTER ROLE {API_ROLE} WITH NOLOGIN PASSWORD NULL"))


def test_reports_the_owner_role_as_not_the_api_role(db_engine):
    url = db_engine.url.render_as_string(hide_password=False)
    response = client_for(url).get("/health/db")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "api_role": False}


def test_reports_the_api_role(api_role_url):
    response = client_for(api_role_url).get("/health/db")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "api_role": True}


def test_unreachable_database_is_a_503_that_leaks_nothing():
    response = client_for("postgresql+psycopg://someone:hunter2@127.0.0.1:1/nowhere").get("/health/db")
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "database_unavailable"
    for leak in ("hunter2", "someone", "127.0.0.1", "nowhere"):
        assert leak not in response.text
