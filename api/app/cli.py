"""Admin commands, run by Reuben (never from the web app).

    python -m app.cli create-admin --email someone@example.com --name "Full Name"
    python -m app.cli delete-empty-profile --email someone@example.com [--yes]
    python -m app.cli reset-staging-accounts [--yes]
    python -m app.cli seed-staging [--parent-email ...] [--sitter-email ...] [--yes] [--replace | --remove]
    python -m app.cli check-supabase  (security: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY)

The person signs in to the web app once first (that creates their Supabase sign-in account), then this
gives them an admin profile. Connects with MIGRATION_DATABASE_URL (the database owner), falling back to
DATABASE_URL locally. Use --user-id instead of the lookup on a local database, which has no Supabase.
"""

import argparse
import os
import sys
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx2 as httpx
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.db import sqlalchemy_url
from app.errors import AppError
from app.models import Profile
from app.services import accounts, staging_reset, staging_seed
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
                print(f"{email} already has a Pacifyco profile, so it can't become an admin.", file=sys.stderr)
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
                print(f"No Pacifyco profile for {email}.", file=sys.stderr)
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


def _supabase() -> tuple[str, str]:
    """Staging's Supabase URL and service-role key, from the environment (never from code or chat)."""
    return os.environ.get("SUPABASE_URL", "").rstrip("/"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def _remove_file(path: str) -> None:
    url, key = _supabase()
    response = httpx.request(
        "DELETE",
        f"{url}/storage/v1/object/documents",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        json={"prefixes": [path]},
        timeout=10,
    )
    response.raise_for_status()


def _remove_sign_in(user_id: uuid.UUID) -> None:
    url, key = _supabase()
    response = httpx.request(
        "DELETE",
        f"{url}/auth/v1/admin/users/{user_id}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=10,
    )
    if response.status_code != 404:  # already gone is fine
        response.raise_for_status()


def reset_staging_accounts(
    confirmed: bool,
    database_url: str,
    remove_file: Callable[[str], None] | None = _remove_file,
    remove_sign_in: Callable[[uuid.UUID], None] | None = _remove_sign_in,
) -> int:
    """Removes every parent and sitter on a staging database (admins stay). Without --yes, only counts."""
    if os.environ.get("ENVIRONMENT", "").strip().lower() == "production":
        print("Refused: ENVIRONMENT is production. This is for staging only.", file=sys.stderr)
        return 1
    host = urlsplit(database_url).hostname or "?"
    url, key = _supabase()
    # Without them the profiles would go but the files and sign-in accounts would stay behind.
    if confirmed and remove_file is _remove_file and not (url and key):
        print(
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY for staging first, so the stored files and "
            "sign-in accounts go too.",
            file=sys.stderr,
        )
        return 1
    engine = create_engine(database_url, connect_args={"connect_timeout": 10})
    try:
        with Session(engine) as db:
            found = staging_reset.find(db)
            summary = (
                f"{found.parents} parents ({found.children} children) and {found.sitters} sitters, "
                f"{found.documents} documents, on the database at {host}"
            )
            if not confirmed:
                print(f"Would remove {summary}. Admins stay. Run again with --yes to remove them.")
                return 0
            staging_reset.delete_all(db, found)
    finally:
        engine.dispose()

    problems = 0
    for path in found.storage_paths:
        try:
            if remove_file:
                remove_file(path)
        except httpx.HTTPError:
            problems += 1
    for user_id in found.profile_ids:
        try:
            if remove_sign_in:
                remove_sign_in(user_id)
        except httpx.HTTPError:
            problems += 1
    print(f"Removed {summary}, with their files and sign-in accounts.")
    if problems:
        print(
            f"{problems} files or sign-in accounts couldn't be removed; delete them in the Supabase dashboard.",
            file=sys.stderr,
        )
        return 1
    return 0


def seed_staging(
    parent_email: str | None, sitter_email: str | None, mode: str, confirmed: bool, database_url: str
) -> int:
    """Staging only. Without --yes, only says what it would do. `mode` is "add", "replace" or "remove"."""
    if os.environ.get("ENVIRONMENT", "").strip().lower() == "production":
        print("Refused: ENVIRONMENT is production. This is for staging only.", file=sys.stderr)
        return 1
    host = urlsplit(database_url).hostname or "?"
    engine = create_engine(database_url, connect_args={"connect_timeout": 10})
    try:
        with Session(engine) as db:
            already = len(staging_seed.seeded_ids(db))
            if not confirmed:
                if mode == "remove":
                    print(f"Would remove the {already} seeded people and their bookings, on the database at {host}.")
                else:
                    print(
                        f"Would {'replace' if mode == 'replace' else 'add'} 12 sitters, 8 families and their "
                        f"bookings on the database at {host}"
                        + (
                            f", with bookings for {parent_email or ''} {sitter_email or ''}".rstrip()
                            if parent_email or sitter_email
                            else ""
                        )
                        + ". Run again with --yes to do it."
                    )
                return 0
            if mode in ("remove", "replace"):
                found = staging_seed.remove(db)
                print(f"Removed {found.parents} seeded families and {found.sitters} seeded sitters.")
                if mode == "remove":
                    return 0
            try:
                summary = staging_seed.seed(db, datetime.now(UTC), parent_email, sitter_email)
            except staging_seed.SeedError as exc:
                db.rollback()
                print(str(exc), file=sys.stderr)
                return 1
    finally:
        engine.dispose()
    print(
        f"Added {summary.sitters} sitters, {summary.families} families ({summary.children} children) and "
        f"{summary.bookings} bookings between them"
        + (f", plus {summary.test_bookings} with your test accounts" if summary.test_bookings else "")
        + ". Seeded people can't sign in and are never emailed."
    )
    for note in summary.notes:
        print(note)
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
    reset = commands.add_parser("reset-staging-accounts", help="staging only: remove every parent and sitter")
    reset.add_argument("--yes", action="store_true", help="actually remove them (otherwise only counts)")
    seed = commands.add_parser("seed-staging", help="staging only: fake sitters, families and bookings")
    seed.add_argument("--parent-email", help="your own test parent account, to get bookings too")
    seed.add_argument("--sitter-email", help="your own test sitter account, to get bookings too")
    seed.add_argument("--yes", action="store_true", help="actually do it (otherwise only says what it would do)")
    again = seed.add_mutually_exclusive_group()
    again.add_argument("--replace", action="store_true", help="remove the earlier seed first")
    again.add_argument("--remove", action="store_true", help="only remove what the seed added")
    commands.add_parser("check-supabase", help="security: tables refuse the public key; storage is private")
    args = parser.parse_args(argv)
    if args.command == "check-supabase":
        return check_supabase_command()
    try:
        if args.command == "reset-staging-accounts":
            return reset_staging_accounts(args.yes, _database_url())
        if args.command == "seed-staging":
            mode = "remove" if args.remove else "replace" if args.replace else "add"
            parent_email = args.parent_email.strip() if args.parent_email else None
            sitter_email = args.sitter_email.strip() if args.sitter_email else None
            return seed_staging(parent_email, sitter_email, mode, args.yes, _database_url())
        if args.command == "delete-empty-profile":
            return delete_empty_profile(args.email.strip(), args.yes, _database_url())
        return create_admin(args.email.strip(), " ".join(args.name.split()), args.user_id, _database_url())
    except OperationalError as exc:
        print(connection_problem(exc), file=sys.stderr)
        return 1


def check_supabase_command() -> int:
    """Prints each check (app/security_check.py) and exits 1 if any fails."""
    from app.security_check import check_storage, check_tables

    url, key = _supabase()
    if not url or not key:
        print("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY first (in your own terminal).", file=sys.stderr)
        return 1
    try:
        anon = os.environ.get("SUPABASE_ANON_KEY", "")
        found = (check_tables(url, anon) if anon else []) + check_storage(url, key)
    except httpx.HTTPError as exc:
        print(f"Couldn't talk to Supabase Storage: {type(exc).__name__}. Check the URL and key.", file=sys.stderr)
        return 1
    if not os.environ.get("SUPABASE_ANON_KEY"):
        print("SKIP  The tables (set SUPABASE_ANON_KEY, the public key, to check them)")
    for item in found:
        print(f"{'PASS' if item.passed else 'FAIL'}  {item.name} ({item.detail})")
    return 0 if all(item.passed for item in found) else 1


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
