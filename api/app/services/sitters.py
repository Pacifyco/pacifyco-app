"""A sitter's own application and profile (CLAUDE.md section 7 steps 1 and 4). Field validation
(ranges, required sub-fields, exactly how many references) happens in the router's request schema,
same as the parent-side services; this module trusts its input and owns the encryption of health
disclosure and bank details."""

import json
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import PayoutMethod, Reference, Sitter
from app.services import encryption

MAX_REFERENCES = 2

# Fixed lists the sitter picks from (UX review 2026-11-13). Pacify takes children from 18 months
# (CLAUDE.md 6.4), so there's no infant group.
AGE_GROUPS = ("Toddler", "Preschool", "School age")
LANGUAGES = ("English", "Kannada", "Hindi", "Tamil", "Malayalam", "Telugu")


def known(values: list[str], allowed: tuple[str, ...]) -> list[str]:
    """Only values from the list, for anything shown to parents (older free-text entries are dropped)."""
    return [value for value in allowed if value in values]


def age_years(dob: date, as_of: date) -> int:
    return as_of.year - dob.year - ((as_of.month, as_of.day) < (dob.month, dob.day))


@dataclass(frozen=True)
class BankDetails:
    account_holder_name: str
    account_number: str
    ifsc_code: str


def _get_sitter(db: Session, sitter_id: uuid.UUID) -> Sitter:
    sitter = db.get(Sitter, sitter_id)
    if sitter is None:  # the sitter row is created at sign-up, so this would mean a bad profile id
        raise AppError(404, "not_found", "Sitter profile not found")
    return sitter


def get_profile(db: Session, sitter_id: uuid.UUID) -> Sitter:
    return _get_sitter(db, sitter_id)


def update_profile(
    db: Session,
    sitter_id: uuid.UUID,
    *,
    date_of_birth: date,
    bio: str | None,
    years_experience: int,
    age_groups: list[str],
    languages: list[str],
    first_aid: bool,
    reference_shared_consent: bool = False,
) -> Sitter:
    sitter = _get_sitter(db, sitter_id)
    sitter.date_of_birth = date_of_birth
    sitter.bio = bio
    sitter.years_experience = years_experience
    sitter.age_groups = age_groups
    sitter.languages = languages
    sitter.first_aid = first_aid
    sitter.reference_shared_consent = reference_shared_consent
    db.commit()
    return sitter


def set_health_disclosure(db: Session, sitter_id: uuid.UUID, disclosure: str | None, encryption_key: str) -> None:
    sitter = _get_sitter(db, sitter_id)
    sitter.health_disclosure_encrypted = (
        encryption.encrypt(encryption_key, disclosure) if disclosure is not None else None
    )
    db.commit()


def get_health_disclosure(db: Session, sitter_id: uuid.UUID, encryption_key: str) -> str | None:
    sitter = _get_sitter(db, sitter_id)
    if sitter.health_disclosure_encrypted is None:
        return None
    return encryption.decrypt(encryption_key, sitter.health_disclosure_encrypted)


def set_payout_bank(db: Session, sitter_id: uuid.UUID, details: BankDetails, encryption_key: str) -> None:
    sitter = _get_sitter(db, sitter_id)
    sitter.payout_method = PayoutMethod.bank
    sitter.bank_details_encrypted = encryption.encrypt(encryption_key, json.dumps(details.__dict__))
    sitter.upi_id = None
    db.commit()


def set_payout_upi(db: Session, sitter_id: uuid.UUID, upi_id: str) -> None:
    sitter = _get_sitter(db, sitter_id)
    sitter.payout_method = PayoutMethod.upi
    sitter.upi_id = upi_id
    sitter.bank_details_encrypted = None
    db.commit()


def get_payout_bank(db: Session, sitter_id: uuid.UUID, encryption_key: str) -> BankDetails | None:
    sitter = _get_sitter(db, sitter_id)
    if sitter.bank_details_encrypted is None:
        return None
    return BankDetails(**json.loads(encryption.decrypt(encryption_key, sitter.bank_details_encrypted)))


# ---------- references (CLAUDE.md section 7 step 4) ----------


def list_references(db: Session, sitter_id: uuid.UUID) -> list[Reference]:
    return list(db.scalars(select(Reference).where(Reference.sitter_id == sitter_id).order_by(Reference.id)))


def add_reference(db: Session, sitter_id: uuid.UUID, name: str, phone: str, relationship: str) -> Reference:
    count = db.scalar(select(func.count()).select_from(Reference).where(Reference.sitter_id == sitter_id))
    if count is not None and count >= MAX_REFERENCES:
        raise AppError(409, "too_many_references", "Only two references are needed")
    reference = Reference(sitter_id=sitter_id, name=name, phone=phone, relationship=relationship)
    db.add(reference)
    db.commit()
    return reference


def remove_reference(db: Session, sitter_id: uuid.UUID, reference_id: uuid.UUID) -> None:
    reference = db.get(Reference, reference_id)
    if reference is None:
        raise AppError(404, "not_found", "That reference isn't on your list")
    if reference.sitter_id != sitter_id:  # no IDOR: can't remove another sitter's reference
        raise AppError(403, "forbidden", "That reference isn't on your list")
    db.delete(reference)
    db.commit()
