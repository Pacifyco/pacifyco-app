"""Admin commands, run by Reuben (never from the web app).

    python -m app.cli create-admin --email someone@example.com --name "Full Name"
    python -m app.cli delete-empty-profile --email someone@example.com [--yes]

The person signs in to the web app once first (that creates their Supabase sign-in account), then this
gives them an admin profile. Connects with MIGRATION_DATABASE_URL (the database owner), falling back to
DATABASE_URL locally. Use --user-id instead of the lookup on a local database, which has no Supabase.
"""

import argparse
import os
import sys
import uuid

from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.db import sqlalchemy_url
from app.errors import AppError
from app.models import Profile
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


def delete_empty_profile(email: str, confirmed: bool, database_url: str) -> int:
    """Without --yes, only says what would be deleted."""
    engine = create_engine(database_url, connect_args={"connect_timeout": 10})
    try:
        with Session(engine) as db:
            profile = db.scalar(select(Profile).where(func.lower(Profile.email) == email.lower()))
            if profile is None:
                print(f"No Pacify profile for {email}.", file=sys.stderr)
                return 1
            if not accounts.is_empty(db, profile):
                print(
                    f"{email}'s {profile.role} account has records, so it can't be deleted this way.", file=sys.stderr
                )
                return 1
            if not confirmed:
                print(f"Would delete the empty {profile.role} profile for {email}. Run again with --yes to delete it.")
                return 0
            accounts.delete_empty_profile(db, email)
    finally:
        engine.dispose()
    print(f"Deleted the {profile.role} profile for {email}. Their sign-in account (in Supabase) is untouched.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin", help="give a signed-in person an admin profile")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)
    admin.add_argument("--user-id", type=uuid.UUID, help="local databases only")
    delete = commands.add_parser("delete-empty-profile", help="remove a profile that holds nothing yet")
    delete.add_argument("--email", required=True)
    delete.add_argument("--yes", action="store_true", help="actually delete (otherwise only checks)")
    args = parser.parse_args(argv)
    try:
        if args.command == "delete-empty-profile":
            return delete_empty_profile(args.email.strip(), args.yes, _database_url())
        return create_admin(args.email.strip(), " ".join(args.name.split()), args.user_id, _database_url())
    except OperationalError as exc:
        print(connection_problem(exc), file=sys.stderr)
        return 1


def connection_problem(exc: OperationalError) -> str:
    """One readable line instead of a traceback. Never includes the URL (it holds the password)."""
    text = str(exc.orig or exc).lower()
    if "tenant/user" in text and "not found" in text:
        hint = "the server in the URL doesn't know this project. Copy the URI from Supabase → Connect → Session pooler."
    elif "password authentication failed" in text:
        hint = "the password in the URL was refused."
    else:
        hint = "check the URL and your internet connection."
    return f"Couldn't connect to the database: {hint}"


if __name__ == "__main__":
    sys.exit(main())
