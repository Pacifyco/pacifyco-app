"""Creating accounts (CLAUDE.md 6.13). Parents and sitters sign themselves up; admins come from the CLI."""

import re
import uuid

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Parent, Profile, ProfileStatus, Role, Sitter
from app.services.service_area import require_in_service_area

# Indian mobile numbers: 10 digits starting 6–9, optionally written with +91, 91 or a leading 0.
_MOBILE = re.compile(r"^(?:\+?91|0)?([6-9]\d{9})$")
SIGN_UP_ROLES = (Role.parent, Role.sitter)


def normalise_mobile(raw: str) -> str | None:
    """'+91 98765-43210' → '+919876543210'. None if it isn't an Indian mobile number."""
    match = _MOBILE.match(re.sub(r"[\s\-().]", "", raw))
    return f"+91{match.group(1)}" if match else None


def _already_signed_up() -> AppError:
    return AppError(409, "already_signed_up", "This account is already set up")


def sign_up(
    db: Session, *, user_id: uuid.UUID, email: str, role: Role, full_name: str, phone: str, pin_code: str
) -> Profile:
    """Create the profile and its parent or sitter record. Status starts as pending (verification)."""
    if role not in SIGN_UP_ROLES:
        raise AppError(422, "role_not_allowed", "Choose parent or sitter")
    require_in_service_area(db, pin_code)
    if db.get(Profile, user_id) is not None:
        raise _already_signed_up()
    if db.scalar(select(Profile.id).where(Profile.email == email)) is not None:
        raise AppError(409, "email_in_use", "This email already has a Pacify account")

    profile = Profile(id=user_id, role=role, full_name=full_name, phone=phone, email=email, pin_code=pin_code)
    db.add(profile)
    db.flush()  # profile first: the parent or sitter row points at it
    db.add(Parent(profile_id=user_id) if role == Role.parent else Sitter(profile_id=user_id))
    try:
        db.commit()
    except IntegrityError as exc:  # the same person signing up twice at once
        db.rollback()
        raise _already_signed_up() from exc
    return profile


def find_auth_user_id(db: Session, email: str) -> uuid.UUID | None:
    """Look up a Supabase sign-in account by email. Needs the database owner role (auth.users isn't
    visible to the API's own role)."""
    return db.scalar(text("SELECT id FROM auth.users WHERE lower(email) = lower(:email)"), {"email": email})


def create_admin(db: Session, *, user_id: uuid.UUID, email: str, full_name: str) -> Profile:
    """An admin profile for someone who has already signed in once. Refuses an existing profile, so an
    admin can't be made from a parent or sitter account."""
    if db.get(Profile, user_id) is not None:
        raise _already_signed_up()
    profile = Profile(id=user_id, role=Role.admin, full_name=full_name, email=email, status=ProfileStatus.active)
    db.add(profile)
    db.commit()
    return profile
