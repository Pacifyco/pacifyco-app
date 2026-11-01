"""Admin commands, run by Reuben (never from the web app).

    python -m app.cli create-admin --email someone@example.com --name "Full Name"

The person signs in to the web app once first (that creates their Supabase sign-in account), then this
gives them an admin profile. Connects with MIGRATION_DATABASE_URL (the database owner), falling back to
DATABASE_URL locally. Use --user-id instead of the lookup on a local database, which has no Supabase.
"""

import argparse
import os
import sys
import uuid

from sqlalchemy import create_engine
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.db import sqlalchemy_url
from app.errors import AppError
from app.services import accounts
from app.settings import get_settings


def _database_url() -> str:
    return sqlalchemy_url(os.environ.get("MIGRATION_DATABASE_URL") or get_settings().effective_database_url)


def create_admin(email: str, name: str, user_id: uuid.UUID | None, database_url: str) -> int:
    engine = create_engine(database_url, connect_args={"connect_timeout": 10})
    try:
        with Session(engine) as db:
            if user_id is None:
                try:
                    user_id = accounts.find_auth_user_id(db, email)
                except ProgrammingError:
                    print("This database has no Supabase sign-in accounts. Pass --user-id.", file=sys.stderr)
                    return 1
                if user_id is None:
                    print(f"No sign-in account for {email}. Ask them to sign in once first.", file=sys.stderr)
                    return 1
            try:
                accounts.create_admin(db, user_id=user_id, email=email, full_name=name)
            except AppError:
                print(f"{email} already has a Pacify profile, so it can't become an admin.", file=sys.stderr)
                return 1
    finally:
        engine.dispose()
    print(f"{email} is now an admin.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin", help="give a signed-in person an admin profile")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)
    admin.add_argument("--user-id", type=uuid.UUID, help="local databases only")
    args = parser.parse_args(argv)
    return create_admin(args.email.strip(), " ".join(args.name.split()), args.user_id, _database_url())


if __name__ == "__main__":
    sys.exit(main())
