import pytest
import sentry_sdk
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from app.errors import AppError
from app.main import SENTRY_DATA_COLLECTION, create_app, init_sentry
from app.settings import Environment, Settings

WEB_ORIGIN = "https://staging.pacifyco.in"
STAGING = {"environment": "staging", "cors_origins": WEB_ORIGIN, "database_url": "postgresql+psycopg://u:p@db/x"}


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
    response = make_client(make_settings(**STAGING)).get("/health")
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
@pytest.mark.parametrize("missing", ["cors_origins", "database_url"])
def test_deployed_environments_require_config(environment, missing):
    values = {**STAGING, "environment": environment, missing: ""}
    with pytest.raises(ValidationError, match=missing.upper()):
        make_settings(**values)


def test_local_database_falls_back_to_docker():
    assert "localhost:5432/pacifyco" in make_settings().effective_database_url
    assert make_settings(database_url="postgresql+psycopg://x").effective_database_url == "postgresql+psycopg://x"


@pytest.mark.parametrize(
    "copied",
    ["postgresql://u:p@pooler.supabase.com:5432/postgres", "postgres://u:p@pooler.supabase.com:5432/postgres"],
)
def test_supabase_urls_use_psycopg_3(copied):
    url = make_settings(database_url=copied).effective_database_url
    assert url == "postgresql+psycopg://u:p@pooler.supabase.com:5432/postgres"


def test_wildcard_cors_origin_rejected():
    with pytest.raises(ValidationError, match="not allowed"):
        make_settings(cors_origins="*")


# ---------- CORS ----------


def preflight(client: TestClient, origin: str):
    return client.options("/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})


def test_cors_allows_listed_origin():
    client = make_client(make_settings(**STAGING))
    response = preflight(client, WEB_ORIGIN)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == WEB_ORIGIN


def test_cors_refuses_other_origins():
    client = make_client(make_settings(**STAGING))
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


def test_sentry_sends_errors_only_and_no_personal_data(monkeypatch):
    calls = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **options: calls.append(options))
    settings = make_settings(
        sentry_dsn="https://key@o1.ingest.de.sentry.io/1",
        environment="staging",
        database_url="postgresql+psycopg://x",
        cors_origins="https://staging.example",
    )
    assert init_sentry(settings) is True
    options = calls[0]
    assert options["environment"] == "staging"
    assert options["traces_sample_rate"] == 0.0
    assert options["send_default_pii"] is False
    assert options["max_request_body_size"] == "never"
    assert options["include_local_variables"] is False
    collection = options["data_collection"]
    assert collection["http_bodies"] == []
    for key in ("user_info", "cookies", "http_headers", "url_query_params", "database_query_data"):
        assert collection[key] is False, key


def test_sentry_accepts_our_privacy_options():
    """The real SDK accepts every option (an unknown one would raise), without sending anything."""
    client = sentry_sdk.Client(dsn="https://key@o1.ingest.de.sentry.io/1", data_collection=SENTRY_DATA_COLLECTION)
    assert client.options["data_collection"]["stack_frame_variables"] is False
    client.close()


def test_crashes_still_carry_cors_headers_and_say_nothing():
    """So the web app shows "something went wrong" rather than "couldn't reach Pacify"."""
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.settings import Settings

    app = create_app(
        Settings(_env_file=None, environment="staging", cors_origins="https://web.example", database_url="x")
    )

    @app.get("/_crash")
    def crash() -> None:
        raise RuntimeError("secret detail")

    response = TestClient(app, raise_server_exceptions=False).get("/_crash", headers={"Origin": "https://web.example"})
    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "https://web.example"
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret detail" not in response.text
