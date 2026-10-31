import os

import pytest
from sqlalchemy import create_engine, text

# Tests run against a real Postgres (CLAUDE.md section 9), never the dev database.
# Locally this is the `pacifyco_test` database from docker-compose.yml; CI sets TEST_DATABASE_URL.
DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://pacifyco:pacifyco@localhost:5432/pacifyco_test"


@pytest.fixture(scope="session")
def db_engine():
    url = os.environ.get("TEST_DATABASE_URL") or DEFAULT_TEST_DATABASE_URL
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            "Can't reach the test database. Start it with `docker compose up -d --wait` "
            f"from the repo root, or set TEST_DATABASE_URL. ({exc.__class__.__name__})",
            pytrace=False,
        )
    yield engine
    engine.dispose()
