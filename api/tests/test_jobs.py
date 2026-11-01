"""/internal/jobs/*: only callable with JOBS_SECRET (CLAUDE.md sections 5 and 9, security testing)."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import jobs
from app.settings import Settings

SECRET = "s3cret-for-tests-only"


def client(db_engine, jobs_secret: str = SECRET) -> TestClient:
    settings = Settings(
        _env_file=None,
        environment="staging",
        cors_origins="https://staging.example",
        database_url=db_engine.url.render_as_string(hide_password=False),
        jobs_secret=jobs_secret,
    )
    return TestClient(create_app(settings), raise_server_exceptions=False)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("run", ["daily", "frequent", "no-such-run"])
@pytest.mark.parametrize(
    "headers",
    [{}, bearer("wrong"), bearer(SECRET + "x"), {"Authorization": SECRET}, bearer("")],
    ids=["missing", "wrong", "longer", "no-bearer-prefix", "empty"],
)
def test_jobs_reject_requests_without_the_secret(db_engine, run, headers):
    response = client(db_engine).post(f"/internal/jobs/{run}", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert SECRET not in response.text


def test_jobs_locked_when_no_secret_is_configured(db_engine):
    response = client(db_engine, jobs_secret="").post("/internal/jobs/daily", headers=bearer(""))
    assert response.status_code == 401


def test_daily_run_keeps_the_database_active(db_engine):
    response = client(db_engine).post("/internal/jobs/daily", headers=bearer(SECRET))
    assert response.status_code == 200
    assert response.json() == {"run": "daily", "ran": ["keep_database_active"]}


def test_frequent_run_has_no_tasks_yet(db_engine):
    response = client(db_engine).post("/internal/jobs/frequent", headers=bearer(SECRET))
    assert response.json() == {"run": "frequent", "ran": []}


def test_unknown_run_is_404_once_authorised(db_engine):
    response = client(db_engine).post("/internal/jobs/weekly", headers=bearer(SECRET))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_job"


def test_jobs_only_accept_post(db_engine):
    assert client(db_engine).get("/internal/jobs/daily", headers=bearer(SECRET)).status_code == 405


def test_each_run_can_be_repeated(db_engine):
    """Jobs must be idempotent: the scheduler may retry a run."""
    c = client(db_engine)
    first = c.post("/internal/jobs/daily", headers=bearer(SECRET)).json()
    second = c.post("/internal/jobs/daily", headers=bearer(SECRET)).json()
    assert first == second


def test_every_task_has_a_unique_name():
    for run, tasks in jobs.RUNS.items():
        names = [name for name, _ in tasks]
        assert len(names) == len(set(names)), run
