"""The parent area. Every route here is for parents only (CLAUDE.md 9: wrong role gets 403)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from app.auth import require_role
from app.deps import DbSession
from app.models import AuthorisedAdult, EmergencyContact, Profile, Role
from app.services import consent, family
from app.services.accounts import normalise_mobile

router = APIRouter(prefix="/parent", tags=["parent"], dependencies=[Depends(require_role(Role.parent))])
Parent = Annotated[Profile, Depends(require_role(Role.parent))]


class ConsentStatus(BaseModel):
    version: str  # the current version
    required_accepted: bool  # every required consent given, at the current version
    accepted_at: datetime | None  # when the last required one was given, if all are
    marketing: bool  # current opt-in state


class AcceptConsent(BaseModel):
    version: str  # the version the parent was shown
    marketing: bool  # whether they also ticked the optional marketing box


class SetMarketing(BaseModel):
    accepted: bool


def _status(summary: consent.ConsentSummary) -> ConsentStatus:
    return ConsentStatus(
        version=summary.version,
        required_accepted=summary.required_accepted,
        accepted_at=summary.accepted_at,
        marketing=summary.marketing,
    )


@router.get("/consent")
def get_consent(parent: Parent, db: DbSession) -> ConsentStatus:
    return _status(consent.summary(db, parent.id))


@router.post("/consent")
def accept_consent(body: AcceptConsent, parent: Parent, db: DbSession) -> ConsentStatus:
    return _status(consent.accept(db, parent.id, body.version, body.marketing))


@router.patch("/consent/marketing")
def set_marketing_consent(body: SetMarketing, parent: Parent, db: DbSession) -> ConsentStatus:
    return _status(consent.set_marketing(db, parent.id, body.accepted))


# ---------- emergency contacts and authorised adults (CLAUDE.md 7, Family Terms 2.5) ----------


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    relationship: str = Field(min_length=1, max_length=50)
    phone: str = Field(max_length=20)

    @field_validator("name", "relationship")
    @classmethod
    def _clean(cls, value: str) -> str:
        cleaned = " ".join(value.split())
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


class SetEmergencyContacts(BaseModel):
    # Exactly two per family (Family Terms 2.5), not per child.
    contacts: list[ContactIn] = Field(min_length=2, max_length=2)


class ContactOut(BaseModel):
    id: uuid.UUID
    name: str
    relationship: str
    phone: str


def _contact_out(row: EmergencyContact | AuthorisedAdult) -> ContactOut:
    return ContactOut(id=row.id, name=row.name, relationship=row.relationship, phone=row.phone)


@router.get("/emergency-contacts")
def get_emergency_contacts(parent: Parent, db: DbSession) -> list[ContactOut]:
    return [_contact_out(row) for row in family.list_emergency_contacts(db, parent.id)]


@router.put("/emergency-contacts")
def put_emergency_contacts(body: SetEmergencyContacts, parent: Parent, db: DbSession) -> list[ContactOut]:
    contacts = [(c.name, c.relationship, c.phone) for c in body.contacts]
    return [_contact_out(row) for row in family.set_emergency_contacts(db, parent.id, contacts)]


@router.get("/authorised-adults")
def get_authorised_adults(parent: Parent, db: DbSession) -> list[ContactOut]:
    return [_contact_out(row) for row in family.list_authorised_adults(db, parent.id)]


@router.post("/authorised-adults", status_code=201)
def post_authorised_adult(body: ContactIn, parent: Parent, db: DbSession) -> ContactOut:
    adult = family.add_authorised_adult(db, parent.id, body.name, body.relationship, body.phone)
    return _contact_out(adult)


@router.delete("/authorised-adults/{adult_id}", status_code=204)
def delete_authorised_adult(adult_id: uuid.UUID, parent: Parent, db: DbSession) -> None:
    family.remove_authorised_adult(db, parent.id, adult_id)
