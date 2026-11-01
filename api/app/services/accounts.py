"""Creating accounts (CLAUDE.md 6.13). Parents and sitters sign themselves up; admins come from the CLI."""

import re
import uuid

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import AuditLog, Child, Consent, LegalAcceptance, Parent, Profile, ProfileStatus, Role, Sitter
from app.services import legal
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
    db: Session,
    *,
    user_id: uuid.UUID,
    email: str,
    role: Role,
    full_name: str,
    phone: str,
    pin_code: str,
    accepted: list[legal.Accepted],
    request: legal.RequestInfo,
) -> Profile:
    """Create the profile, its parent or sitter record and the terms acceptances, all or nothing.
    Status starts as pending (verification). Sign-up can't complete without accepting the terms."""
    if role not in SIGN_UP_ROLES:
        raise AppError(422, "role_not_allowed", "Choose parent or sitter")
    require_in_service_area(db, pin_code)
    documents = legal.check_accepted(db, role, accepted)
    if db.get(Profile, user_id) is not None:
        raise _already_signed_up()
    if db.scalar(select(Profile.id).where(Profile.email == email)) is not None:
        raise AppError(409, "email_in_use", "This email already has a Pacify account")

    profile = Profile(id=user_id, role=role, full_name=full_name, phone=phone, email=email, pin_code=pin_code)
    db.add(profile)
    db.flush()  # profile first: the parent or sitter row points at it
    db.add(Parent(profile_id=user_id) if role == Role.parent else Sitter(profile_id=user_id))
    db.flush()
    legal.record_acceptances(db, user_id, documents, request)
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


def is_empty(db: Session, profile: Profile) -> bool:
    """True while the account holds nothing but its sign-up details (CLAUDE.md 6.13): no children, no
    consent records, no sitter application details and no audit history. Add each new table that
    belongs to a person here (documents, onboarding steps, packs, bookings...) when its phase creates it."""
    if db.scalar(select(Child.id).where(Child.parent_id == profile.id).limit(1)) is not None:
        return False
    if db.scalar(select(AuditLog.id).where(AuditLog.actor_id == profile.id).limit(1)) is not None:
        return False
    if db.scalar(select(Consent.id).where(Consent.parent_id == profile.id).limit(1)) is not None:
        return False  # consent records are kept
    sitter = db.get(Sitter, profile.id)
    if sitter is not None:
        filled = (
            sitter.date_of_birth,
            sitter.health_disclosure_encrypted,
            sitter.payout_method,
            sitter.bank_details_encrypted,
            sitter.upi_id,
            sitter.bio,
            sitter.years_experience,
            sitter.hourly_rate_paise,
        )
        if any(value is not None for value in filled) or sitter.age_groups or sitter.languages:
            return False
    return True


def delete_empty_profile(db: Session, email: str) -> Profile:
    """Remove a Pacify profile that holds nothing yet, e.g. a test account or one left behind when its
    Supabase sign-in account was deleted. Refuses anything with real records."""
    profile = db.scalar(select(Profile).where(func.lower(Profile.email) == email.lower()))
    if profile is None:
        raise AppError(404, "not_found", "No Pacify profile with this email")
    if not is_empty(db, profile):
        raise AppError(409, "profile_not_empty", "This account has records, so it can't be deleted this way")
    # Terms acceptances alone don't make an account non-empty: nothing happened under those terms. The
    # API role can't delete them; this runs from the CLI as the database owner.
    db.execute(delete(LegalAcceptance).where(LegalAcceptance.profile_id == profile.id))
    db.delete(profile)  # its parents or sitters row goes with it (ON DELETE CASCADE)
    db.commit()
    return profile
