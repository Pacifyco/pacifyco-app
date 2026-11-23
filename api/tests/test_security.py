# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Security testing (CLAUDE.md 9; phase 12) that isn't covered elsewhere: secure headers, API docs off
outside local, rate limits, no secrets in the repository or the logs, and the storage checks.

Covered in their own files: IDOR (test_idor.py), the role gates over every endpoint (test_roles.py), RLS
and the browser roles' table access (test_migrations.py), upload type and size (test_documents.py), CORS
and errors that never echo what was sent (test_skeleton.py), jobs refusing calls without JOBS_SECRET
(test_jobs.py), and Sentry sending no personal data (test_skeleton.py).
"""

import re
import subprocess
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import rate_limits, security_check
from app.main import create_app
from app.services import storage as storage_service
from app.settings import Settings
from tests.test_documents import cleanup_documents, client, parent, storage  # noqa: F401  (fixtures)
from tests.test_marketplace import finished_parent  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, user  # noqa: F401  (fixture)

REPO = Path(__file__).resolve().parents[2]
STAGING = {
    "environment": "staging",
    "cors_origins": "https://staging.example",
    "database_url": "postgresql+psycopg://u:p@db/x",
    "jobs_secret": "x",
    "public_web_url": "https://staging.example",
}


def app_client(**settings) -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, **settings)), raise_server_exceptions=False)


# ---------- secure headers and the API docs ----------


@pytest.mark.parametrize("path", ["/health", "/no-such-page", "/me"])  # a success, a 404 and a 401
def test_every_response_has_the_secure_headers(path):
    response = app_client().get(path)
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert response.headers["cache-control"] == "no-store"
    assert "strict-transport-security" not in response.headers  # local is plain HTTP


def test_outside_local_https_is_required_and_the_docs_are_off():
    staging = app_client(**STAGING)
    assert staging.get("/health").headers["strict-transport-security"].startswith("max-age=31536000")
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert staging.get(path).status_code == 404, path
    assert app_client().get("/openapi.json").status_code == 200  # still there locally, for development


# ---------- rate limits ----------


def limited_routes() -> dict[str, str]:
    """Each endpoint with a rate limit, and the limit's scope."""
    found = {}
    for route in create_app(Settings(_env_file=None)).routes:
        for context in getattr(route, "effective_route_contexts", lambda: [])():
            for dependency in context.dependant.dependencies:
                if getattr(dependency.call, "__qualname__", "").startswith("rate_limited."):
                    found[f"{sorted(context.methods)[0]} {context.path}"] = dependency.call
    return found


def test_sign_up_booking_paying_complaints_and_uploads_are_limited():
    assert set(limited_routes()) == {
        "POST /me/profile",
        "POST /parent/bookings",
        "POST /parent/bookings/{booking_id}/payment",
        "POST /parent/payments/{payment_id}/payment",
        "POST /me/complaints",
        "POST /me/complaints/{complaint_id}/messages",
        "POST /documents/upload-url",
    }


def test_too_many_sign_up_attempts_are_refused_for_that_person_only(client, db_engine):
    rate_limits.limiter.reset()
    who = {"id": uuid.uuid4(), "email": f"{uuid.uuid4()}@example.com"}
    someone_else = {"id": uuid.uuid4(), "email": f"{uuid.uuid4()}@example.com"}
    try:
        tries = [client.post("/me/profile", json=PARENT, headers=auth_for(who)) for _ in range(6)]
        assert [item.status_code for item in tries[:2]] == [201, 409]  # signed up, then already signed up
        refused = tries[-1]
        assert refused.status_code == 429 and refused.json()["error"]["code"] == "rate_limited"
        assert client.post("/me/profile", json=PARENT, headers=auth_for(someone_else)).status_code == 201
    finally:
        rate_limits.limiter.reset()
        for person in (who, someone_else):
            cleanup_documents(db_engine, person["id"])


def test_complaints_are_limited_per_hour(client, finished_parent):
    rate_limits.limiter.reset()
    body = {"type": "other", "description": "Something."}
    sent = [client.post("/me/complaints", json=body, headers=auth_for(finished_parent)) for _ in range(11)]
    assert [item.status_code for item in sent[:10]] == [201] * 10
    assert sent[10].status_code == 429 and sent[10].json()["error"]["code"] == "rate_limited"
    rate_limits.limiter.reset()


def test_a_rate_limit_is_counted_without_a_signed_in_person_being_trusted(client):
    """No token, no count: the limit runs after the token is verified, so a forged one gets 401 first."""
    response = client.post("/me/profile", json=PARENT, headers={"Authorization": "Bearer forged"})
    assert response.status_code == 401


# ---------- secrets ----------

SECRET_PATTERNS = {
    "a Supabase secret key": re.compile(r"sb_secret_[A-Za-z0-9_-]{10,}"),
    "a Resend API key": re.compile(r"\bre_[A-Za-z0-9]{8,}_[A-Za-z0-9]{8,}"),
    "a private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "a JWT (such as a service-role key)": re.compile(
        r"\beyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"
    ),
    "a Sentry DSN with its key": re.compile(r"https://[0-9a-f]{32}@[a-z0-9.]*sentry\.io/\d+"),
    # Not the local and test databases' own (pacifyco, p), a "<placeholder>" or the tests' dummy (hunter2).
    "a database URL with a password": re.compile(
        r"postgres(?:ql)?(?:\+\w+)?://[^:\s/]+:(?!p@|pacifyco@|<|hunter2@)[^@\s]{6,}@"
    ),
    "a filled-in secret setting": re.compile(
        r"^(SUPABASE_SERVICE_ROLE_KEY|RESEND_API_KEY|JOBS_SECRET|FIELD_ENCRYPTION_KEY|SENTRY_DSN)=\S+", re.M
    ),
}


def tracked_files() -> list[Path]:
    listed = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    return [REPO / name for name in listed.splitlines()]


def test_no_secrets_are_committed():
    files = tracked_files()
    assert len(files) > 200  # the scan sees the repository
    assert not [path for path in files if path.name.startswith(".env") and path.name != ".env.example"]
    found = []
    for path in files:
        if path.suffix in {".png", ".jpg", ".jpeg", ".ico", ".woff", ".woff2", ".pdf", ".docx", ".pyc"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError, FileNotFoundError:
            continue
        for what, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                found.append(f"{path.relative_to(REPO)}: {what}")
    assert found == []


def test_logs_never_include_keys_tokens_or_addresses():
    """Every log line the API writes is a fixed message: nothing from the request, the settings or a person."""
    calls = []
    for path in (REPO / "api" / "app").rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if re.search(r"\blogger\.(debug|info|warning|error|exception|critical)\(", line):
                calls.append(line.strip())
    assert calls  # the scan found the log calls
    for line in calls:
        message = re.search(r"\(\s*(f?)\"", line)
        assert message and message.group(1) == "", f"log messages are fixed text, not f-strings: {line}"
        assert "%" not in line.split('"')[1], f"no values formatted into log messages: {line}"


# ---------- storage ----------


def test_view_urls_last_two_minutes(monkeypatch):
    sent = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"signedURL": "/object/sign/documents/a?token=t"}

    def post(url, headers, json, timeout):
        sent.update(url=url, json=json)
        return Response()

    monkeypatch.setattr(storage_service.httpx, "post", post)
    client_ = storage_service.SupabaseStorage(Settings(_env_file=None, supabase_url="https://x.supabase.co"))
    client_.create_signed_view_url("owner/doc")
    assert sent["json"] == {"expiresIn": 120} and storage_service.VIEW_URL_EXPIRY_SECONDS <= 300


class FakeStorage:
    """Stands in for Supabase Storage in the staging check's own tests."""

    def __init__(self, public=False, readable_anonymously=False, expires=True):
        self.public, self.readable, self.expires, self.deleted, self.slept = (
            public,
            readable_anonymously,
            expires,
            [],
            0,
        )

    def response(self, status=200, body=None):
        class Response:
            status_code = status

            def raise_for_status(self_):
                if status >= 400:
                    raise RuntimeError(status)

            def json(self_):
                return body or {}

        return Response()

    def get(self, url, headers=None, timeout=None):
        if "/bucket/" in url:
            return self.response(body={"public": self.public})
        if "/object/public/" in url or ("/object/documents/" in url and not headers):
            return self.response(200 if self.readable else 400)
        expired = self.slept and self.expires
        return self.response(400 if expired else 200)

    def post(self, url, headers=None, json=None, timeout=None):
        if "/upload/sign/" in url:
            return self.response(body={"token": "t"})
        return self.response(body={"signedURL": "/object/sign/documents/x?token=v"})

    def put(self, url, content=None, headers=None, timeout=None):
        return self.response()

    def request(self, method, url, headers=None, json=None, timeout=None):
        self.deleted.append(json)
        return self.response()


@pytest.mark.parametrize(
    "setup, failing",
    [
        ({}, []),
        ({"public": True}, ["The documents bucket is private"]),
        (
            {"readable_anonymously": True},
            ["A file can't be read without a signed URL", "A file can't be read without a key"],
        ),
        ({"expires": False}, ["A signed URL stops working once expired"]),
    ],
)
def test_the_staging_storage_check_reports_each_problem(monkeypatch, setup, failing):
    fake = FakeStorage(**setup)
    for name in ("get", "post", "put", "request"):
        monkeypatch.setattr(security_check.httpx, name, getattr(fake, name))

    def sleep(seconds):
        fake.slept = seconds

    found = security_check.check_storage("https://x.supabase.co", "key", sleep=sleep)
    assert [item.name for item in found if not item.passed] == failing
    assert len(found) == 5 and fake.slept >= security_check.EXPIRES_IN
    assert fake.deleted and fake.deleted[0]["prefixes"][0].startswith("security-check/")  # cleaned up


def test_the_staging_table_check_passes_only_on_a_real_refusal(monkeypatch):
    replies = {
        "profiles": (200, [{"id": "x"}]),  # rows came back: a leak
        "children": (401, {"code": "42501"}),  # refused
        "documents": (404, {"code": "PGRST205"}),  # not exposed at all
        "payments": (503, {"code": "PGRST002"}),  # the REST API didn't answer: not tested
        "bookings": (500, None),
    }

    class Response:
        def __init__(self, status, body):
            self.status_code, self._body = status, body

        def json(self):
            if self._body is None:
                raise ValueError("no body")
            return self._body

    def get(url, headers=None, timeout=None):
        table = url.split("/rest/v1/")[1].split("?")[0]
        return Response(*replies.get(table, (200, [])))  # the rest: allowed, but no rows (RLS, no policies)

    monkeypatch.setattr(security_check.httpx, "get", get)
    found = {item.name.rsplit(" ", 1)[1]: item for item in security_check.check_tables("https://x.supabase.co", "k")}
    assert {name: item.passed for name, item in found.items()} == {
        "profiles": False,
        "children": True,
        "documents": True,
        "payments": False,
        "bookings": False,
        "sitters": True,
        "messages": True,
        "audit_log": True,
    }
    assert found["payments"].detail == "503 PGRST002: not tested, the REST API didn't answer properly"
    assert "x" not in found["profiles"].detail  # never the data itself
