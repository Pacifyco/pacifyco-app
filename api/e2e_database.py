"""A fresh, migrated database for the end-to-end tests (web/e2e). Run from the api folder:

    python e2e_database.py

Drops and recreates the `pacifyco_e2e` database on the local (or CI) Postgres, then runs every migration.
Never point E2E_SERVER_URL at a real environment: it drops a database.
"""

import os
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

SERVER_URL = os.environ.get("E2E_SERVER_URL", "postgresql+psycopg://pacifyco:pacifyco@localhost:5432/postgres")
NAME = "pacifyco_e2e"


def main() -> int:
    if "localhost" not in SERVER_URL and "127.0.0.1" not in SERVER_URL:
        print("Refusing: the end-to-end database must be on localhost.", file=sys.stderr)
        return 1
    engine = create_engine(SERVER_URL, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {NAME} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {NAME}"))
    engine.dispose()

    database_url = SERVER_URL.rsplit("/", 1)[0] + f"/{NAME}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    print(f"{NAME} is ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
