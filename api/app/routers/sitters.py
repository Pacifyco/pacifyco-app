"""The sitter area. Every route here is for sitters only (CLAUDE.md 9: wrong role gets 403)."""

import re
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator, model_validator

from app.auth import require_role
from app.deps import DbSession
from app.models import PayoutMethod, Profile, Reference, Role, Sitter, VerificationStatus
from app.services import sitters as sitters_service
from app.services.accounts import normalise_mobile
from app.settings import Settings, get_settings

router = APIRouter(prefix="/sitter", tags=["sitter"], dependencies=[Depends(require_role(Role.sitter))])
SitterProfile = Annotated[Profile, Depends(require_role(Role.sitter))]
AppSettings = Annotated[Settings, Depends(get_settings)]

MIN_AGE_YEARS = 18


def _clean_text(value: str) -> str:
    return " ".join(value.split())


# ---------- profile (CLAUDE.md section 7 step 1) ----------


class SitterProfileIn(BaseModel):
    date_of_birth: date
    bio: str | None = Field(default=None, max_length=2000)
    years_experience: int = Field(ge=0, le=80)
    age_groups: list[str] = Field(default_factory=list, max_length=10)
    languages: list[str] = Field(default_factory=list, max_length=10)
    first_aid: bool

    @field_validator("date_of_birth")
    @classmethod
    def _at_least_18(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("That date hasn't happened yet")
        if sitters_service.age_years(value, date.today()) < MIN_AGE_YEARS:
            raise ValueError("Sitters must be at least 18 years old")
        return value

    @field_validator("bio")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return (_clean_text(value) or None) if value is not None else None

    @field_validator("age_groups", "languages")
    @classmethod
    def _clean_list(cls, values: list[str]) -> list[str]:
        cleaned = [_clean_text(value) for value in values]
        return [value for value in cleaned if value]


class SitterProfileOut(BaseModel):
    date_of_birth: date | None
    bio: str | None
    years_experience: int | None
    age_groups: list[str]
    languages: list[str]
    first_aid: bool
    onboarding_status: str


def _profile_out(row: Sitter) -> SitterProfileOut:
    return SitterProfileOut(
        date_of_birth=row.date_of_birth,
        bio=row.bio,
        years_experience=row.years_experience,
        age_groups=row.age_groups,
        languages=row.languages,
        first_aid=row.first_aid,
        onboarding_status=row.onboarding_status,
    )


@router.get("/profile")
def get_profile(sitter: SitterProfile, db: DbSession) -> SitterProfileOut:
    return _profile_out(sitters_service.get_profile(db, sitter.id))


@router.put("/profile")
def put_profile(body: SitterProfileIn, sitter: SitterProfile, db: DbSession) -> SitterProfileOut:
    row = sitters_service.update_profile(
        db,
        sitter.id,
        date_of_birth=body.date_of_birth,
        bio=body.bio,
        years_experience=body.years_experience,
        age_groups=body.age_groups,
        languages=body.languages,
        first_aid=body.first_aid,
    )
    return _profile_out(row)


# ---------- health disclosure (CLAUDE.md section 7 step 1: encrypted, admin-only, never shown to parents) ----------


class HealthDisclosure(BaseModel):
    disclosure: str | None = Field(default=None, max_length=4000)

    @field_validator("disclosure")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return (_clean_text(value) or None) if value is not None else None


@router.get("/health-disclosure")
def get_health_disclosure(sitter: SitterProfile, db: DbSession, settings: AppSettings) -> HealthDisclosure:
    return HealthDisclosure(
        disclosure=sitters_service.get_health_disclosure(db, sitter.id, settings.field_encryption_key)
    )


@router.put("/health-disclosure")
def put_health_disclosure(
    body: HealthDisclosure, sitter: SitterProfile, db: DbSession, settings: AppSettings
) -> HealthDisclosure:
    sitters_service.set_health_disclosure(db, sitter.id, body.disclosure, settings.field_encryption_key)
    return body


# ---------- payout details (CLAUDE.md sections 6.2 and 7: bank account or UPI) ----------

_UPI_ID = r"^[\w.\-]{2,256}@[\w.\-]{2,64}$"


class PayoutDetailsIn(BaseModel):
    method: PayoutMethod
    account_holder_name: str | None = Field(default=None, max_length=100)
    account_number: str | None = Field(default=None, max_length=34)
    ifsc_code: str | None = Field(default=None, max_length=11)
    upi_id: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def _required_for_method(self) -> PayoutDetailsIn:
        if self.method == PayoutMethod.bank:
            missing = [v is None for v in (self.account_holder_name, self.account_number, self.ifsc_code)]
            if any(missing):
                raise ValueError("Please fill in the account holder name, account number and IFSC code")
        elif self.method == PayoutMethod.upi:
            if not self.upi_id or not re.match(_UPI_ID, self.upi_id):
                raise ValueError("Please enter a valid UPI ID")
        return self


class PayoutDetailsOut(BaseModel):
    method: PayoutMethod | None
    account_holder_name: str | None = None
    account_number: str | None = None
    ifsc_code: str | None = None
    upi_id: str | None = None


@router.get("/payout-details")
def get_payout_details(sitter: SitterProfile, db: DbSession, settings: AppSettings) -> PayoutDetailsOut:
    row = sitters_service.get_profile(db, sitter.id)
    if row.payout_method == PayoutMethod.bank:
        bank = sitters_service.get_payout_bank(db, sitter.id, settings.field_encryption_key)
        return PayoutDetailsOut(
            method=PayoutMethod.bank,
            account_holder_name=bank.account_holder_name if bank else None,
            account_number=bank.account_number if bank else None,
            ifsc_code=bank.ifsc_code if bank else None,
        )
    if row.payout_method == PayoutMethod.upi:
        return PayoutDetailsOut(method=PayoutMethod.upi, upi_id=row.upi_id)
    return PayoutDetailsOut(method=None)


@router.put("/payout-details")
def put_payout_details(
    body: PayoutDetailsIn, sitter: SitterProfile, db: DbSession, settings: AppSettings
) -> PayoutDetailsOut:
    if body.method == PayoutMethod.bank:
        details = sitters_service.BankDetails(
            account_holder_name=_clean_text(body.account_holder_name or ""),
            account_number=_clean_text(body.account_number or ""),
            ifsc_code=_clean_text(body.ifsc_code or ""),
        )
        sitters_service.set_payout_bank(db, sitter.id, details, settings.field_encryption_key)
        return PayoutDetailsOut(method=PayoutMethod.bank, **details.__dict__)
    sitters_service.set_payout_upi(db, sitter.id, body.upi_id or "")
    return PayoutDetailsOut(method=PayoutMethod.upi, upi_id=body.upi_id)


# ---------- references (CLAUDE.md section 7 step 4) ----------


class ReferenceIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    relationship: str = Field(min_length=1, max_length=50)
    phone: str = Field(max_length=20)

    @field_validator("name", "relationship")
    @classmethod
    def _clean(cls, value: str) -> str:
        cleaned = _clean_text(value)
        if not cleaned:
            raise ValueError("Please fill this in")
        return cleaned

    @field_validator("phone")
    @classmethod
    def _indian_mobile(cls, value: str) -> str:
        phone = normalise_mobile(value)
        if phone is None:
            raise ValueError("Please enter a 10-digit Indian mobile number")
        return phone


class ReferenceOut(BaseModel):
    id: uuid.UUID
    name: str
    relationship: str
    phone: str
    outcome: VerificationStatus


def _reference_out(row: Reference) -> ReferenceOut:
    return ReferenceOut(id=row.id, name=row.name, relationship=row.relationship, phone=row.phone, outcome=row.outcome)


@router.get("/references")
def get_references(sitter: SitterProfile, db: DbSession) -> list[ReferenceOut]:
    return [_reference_out(row) for row in sitters_service.list_references(db, sitter.id)]


@router.post("/references", status_code=201)
def post_reference(body: ReferenceIn, sitter: SitterProfile, db: DbSession) -> ReferenceOut:
    reference = sitters_service.add_reference(db, sitter.id, body.name, body.phone, body.relationship)
    return _reference_out(reference)


@router.delete("/references/{reference_id}", status_code=204)
def delete_reference(reference_id: uuid.UUID, sitter: SitterProfile, db: DbSession) -> None:
    sitters_service.remove_reference(db, sitter.id, reference_id)
