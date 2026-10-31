import pytest
import sentry_sdk
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from app.errors import AppError
from app.main import create_app, init_sentry
from app.settings import Environment, Settings

WEB_ORIGIN = "https://staging.pacifyco.in"


def make_settings(**overrides) -> Settings:
    # _env_file=None: tests never read the developer's real .env
    return Settings(_env_file=None, **overrides)


def make_client(settings: Settings | None = None) -> TestClient:
    app = create_app(settings or make_settings())

    router = APIRouter()

    class Body(BaseModel):
        hours: int

    @router.post("/_test/validate")
    def validate(body: Body) -> dict:
        return {"hours": body.hours}

    @router.get("/_test/app-error")
    def app_error() -> None:
        raise AppError(409, "slot_taken", "That time is already booked", {"slot": "10:00"})

    @router.get("/_test/crash")
    def crash() -> None:
        raise RuntimeError("database password is hunter2")

    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


# ---------- health ----------


def test_health_ok():
    response = make_client(make_settings(environment="staging", cors_origins=WEB_ORIGIN)).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "staging"}


# ---------- settings ----------


def test_settings_default_to_local():
    settings = make_settings()
    assert settings.environment == Environment.local
    assert settings.allowed_origins == ["http://localhost:5173"]


def test_blank_environment_means_local():
    assert make_settings(environment="").environment == Environment.local


def test_comma_lists_are_split_and_trimmed():
    settings = make_settings(
        cors_origins=" https://a.pacifyco.in/ , https://b.pacifyco.in ,",
        admin_alert_emails="a@x.in, b@x.in",
    )
    assert settings.cors_origins == ["https://a.pacifyco.in", "https://b.pacifyco.in"]
    assert settings.admin_alert_emails == ["a@x.in", "b@x.in"]


def test_comma_lists_read_from_environment_variables(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://a.pacifyco.in,https://b.pacifyco.in")
    assert make_settings().cors_origins == ["https://a.pacifyco.in", "https://b.pacifyco.in"]


def test_unknown_environment_rejected():
    with pytest.raises(ValidationError):
        make_settings(environment="prod")


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_deployed_environments_require_cors_origins(environment):
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        make_settings(environment=environment)


def test_wildcard_cors_origin_rejected():
    with pytest.raises(ValidationError, match="not allowed"):
        make_settings(cors_origins="*")


# ---------- CORS ----------


def preflight(client: TestClient, origin: str):
    return client.options(
        "/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"}
    )


def test_cors_allows_listed_origin():
    client = make_client(make_settings(environment="staging", cors_origins=WEB_ORIGIN))
    response = preflight(client, WEB_ORIGIN)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == WEB_ORIGIN


def test_cors_refuses_other_origins():
    client = make_client(make_settings(environment="staging", cors_origins=WEB_ORIGIN))
    response = preflight(client, "https://evil.example")
    assert "access-control-allow-origin" not in response.headers
    simple = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in simple.headers


def test_cors_local_default_allows_vite_dev_server():
    response = preflight(make_client(), "http://localhost:5173")
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


# ---------- error format ----------


def assert_error_shape(body: dict, code: str):
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code


def test_not_found_uses_error_format():
    response = make_client().get("/no-such-route")
    assert response.status_code == 404
    assert_error_shape(response.json(), "not_found")


def test_method_not_allowed_uses_error_format():
    response = make_client().post("/health")
    assert response.status_code == 405
    assert_error_shape(response.json(), "method_not_allowed")


def test_validation_error_lists_fields_without_echoing_input():
    response = make_client().post("/_test/validate", json={"hours": "secret-value"})
    assert response.status_code == 422
    body = response.json()
    assert_error_shape(body, "validation_error")
    assert body["error"]["details"][0]["field"] == "body.hours"
    assert "secret-value" not in response.text


def test_app_error_uses_its_code_and_details():
    response = make_client().get("/_test/app-error")
    assert response.status_code == 409
    assert response.json() == {
        "error": {"code": "slot_taken", "message": "That time is already booked", "details": {"slot": "10:00"}}
    }


def test_unhandled_error_is_generic_and_leaks_nothing():
    response = make_client().get("/_test/crash")
    assert response.status_code == 500
    assert_error_shape(response.json(), "internal_error")
    assert "hunter2" not in response.text
    assert "RuntimeError" not in response.text


# ---------- Sentry ----------


def test_sentry_off_without_dsn():
    assert init_sentry(make_settings()) is False
    assert not sentry_sdk.get_client().is_active()
