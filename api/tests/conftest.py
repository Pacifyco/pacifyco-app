import os
import re
from decimal import Decimal

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


# Approximate centres of the launch pin codes; the fake geocoder answers from the pin code in the query.
PIN_CODE_POSITIONS = {
    "560001": ("12.976600", "77.599300"),
    "560034": ("12.935200", "77.624500"),
    "560038": ("12.978300", "77.640800"),
    "560078": ("12.906300", "77.585700"),
    "560084": ("13.012500", "77.627700"),
    "560095": ("12.934500", "77.626600"),
    "560103": ("12.925600", "77.676100"),
}


class FakeGeocoder:
    """Stands in for Nominatim: tests never make network requests. Records each query it was asked."""

    queries: list[str] = []

    def lookup(self, query: str):
        FakeGeocoder.queries.append(query)
        match = re.search(r"\b(\d{6})\b", query)
        if not match or match.group(1) not in PIN_CODE_POSITIONS:
            return None
        lat, lng = PIN_CODE_POSITIONS[match.group(1)]
        return Decimal(lat), Decimal(lng)


@pytest.fixture(autouse=True)
def fake_geocoder(monkeypatch):
    from app.services import geocoding  # imported here so collecting tests doesn't need the app

    FakeGeocoder.queries = []
    monkeypatch.setattr(geocoding.NominatimGeocoder, "lookup", FakeGeocoder.lookup)
    return FakeGeocoder


class Mailbox:
    """Stands in for Resend (app.services.email): keeps every email instead of sending it."""

    def __init__(self) -> None:
        self.sent = []

    def send(self, email) -> None:
        self.sent.append(email)


@pytest.fixture
def mailbox():
    return Mailbox()
