"""Sign-in tokens: only valid Supabase access tokens for our project get through (CLAUDE.md 9)."""

import time
import uuid

import jwt
import pytest
from alembic import command
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import KeySource, get_key_source, jwks_url
from app.main import create_app
from app.settings import Settings
from tests.test_migrations import alembic_config

SUPABASE_URL = "https://testproject.supabase.co"
ISSUER = f"{SUPABASE_URL}/auth/v1"
OUR_KEY = ec.generate_private_key(ec.SECP256R1())
OTHER_KEY = ec.generate_private_key(ec.SECP256R1())


class FakeKeys(KeySource):
    """Stands in for the project's JWKS: always answers with our test public key."""

    def __init__(self) -> None:
        super().__init__("unused")

    def signing_key(self, token: str) -> object:
        jwt.get_unverified_header(token)  # malformed tokens fail here, as with the real client
        return OUR_KEY.public_key()


def make_settings(db_engine, supabase_url: str = SUPABASE_URL) -> Settings:
    return Settings(
        _env_file=None,
        environment="staging",
        cors_origins="https://staging.example",
        database_url=db_engine.url.render_as_string(hide_password=False),
        supabase_url=supabase_url,
    )


@pytest.fixture
def client(db_engine):
    command.upgrade(alembic_config(db_engine), "head")
    app = create_app(make_settings(db_engine))
    app.dependency_overrides[get_key_source] = FakeKeys
    return TestClient(app, raise_server_exceptions=False)


def token(key=OUR_KEY, algorithm: str = "ES256", **overrides) -> str:
    now = int(time.time())
    claims = {
        "sub": str(uuid.uuid4()),
        "email": "parent@example.com",
        "aud": "authenticated",
        "role": "authenticated",
        "iss": ISSUER,
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    claims = {name: value for name, value in claims.items() if value is not None}
    return jwt.encode(claims, key, algorithm=algorithm)


def bearer(value: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {value}"}


def test_signed_in_without_a_profile_yet(client):
    response = client.get("/me", headers=bearer(token()))
    assert response.status_code == 200
    assert response.json() == {"email": "parent@example.com", "profile": None, "terms_to_accept": []}


def test_loads_the_profile_and_role(client, db_engine):
    user_id = uuid.uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO profiles (id, role, full_name, email) VALUES (:id, 'sitter', 'Asha K', :email)"),
            {"id": user_id, "email": f"{user_id}@example.com"},
        )
    try:
        response = client.get("/me", headers=bearer(token(sub=str(user_id))))
        assert response.status_code == 200
        assert response.json()["profile"] == {"role": "sitter", "status": "pending", "full_name": "Asha K"}
    finally:
        with db_engine.begin() as conn:
            conn.execute(text("DELETE FROM profiles WHERE id = :id"), {"id": user_id})


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer"},
        {"Authorization": "Basic abc"},
        bearer("not-a-jwt"),
    ],
)
def test_missing_or_malformed_token_is_401(client, headers):
    response = client.get("/me", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(
    "bad_token",
    [
        pytest.param(lambda: token(key=OTHER_KEY), id="signed-by-another-key"),
        pytest.param(lambda: token(exp=int(time.time()) - 120), id="expired"),
        pytest.param(lambda: token(aud="someone-else"), id="wrong-audience"),
        pytest.param(lambda: token(iss="https://otherproject.supabase.co/auth/v1"), id="other-project"),
        pytest.param(lambda: token(role="anon"), id="anon-role"),
        pytest.param(lambda: token(role="service_role"), id="service-role"),
        pytest.param(lambda: token(sub="not-a-uuid"), id="bad-subject"),
        pytest.param(lambda: token(exp=None), id="no-expiry"),
        pytest.param(lambda: token(key="a-guessed-shared-secret-that-is-long-enough", algorithm="HS256"), id="hs256"),
        pytest.param(lambda: jwt.encode({"sub": str(uuid.uuid4())}, None, algorithm="none"), id="alg-none"),
    ],
)
def test_invalid_tokens_are_401(client, bad_token):
    response = client.get("/me", headers=bearer(bad_token()))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_fails_closed_without_supabase_config(db_engine):
    command.upgrade(alembic_config(db_engine), "head")
    app = create_app(make_settings(db_engine, supabase_url=""))
    response = TestClient(app).get("/me", headers=bearer(token()))
    assert response.status_code == 401


def test_unreachable_key_server_is_503(db_engine):
    command.upgrade(alembic_config(db_engine), "head")
    app = create_app(make_settings(db_engine, supabase_url="http://127.0.0.1:1"))
    response = TestClient(app, raise_server_exceptions=False).get("/me", headers=bearer(token()))
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "auth_unavailable"


def test_jwks_url_comes_from_the_project_url():
    settings = Settings(_env_file=None, supabase_url="https://abc.supabase.co/")
    assert jwks_url(settings) == "https://abc.supabase.co/auth/v1/.well-known/jwks.json"
    override = Settings(_env_file=None, supabase_url="https://abc.supabase.co", supabase_jwks_url="https://k.example/j")
    assert jwks_url(override) == "https://k.example/j"
