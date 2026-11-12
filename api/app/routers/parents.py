"""The parent area. Every route here is for parents only (CLAUDE.md 9: wrong role gets 403)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime, BaseModel, Field, field_validator

from app.auth import require_role
from app.deps import DbSession
from app.errors import AppError
from app.models import AuthorisedAdult, Child, EmergencyContact, Profile, Role, SitterLevel, VerificationStatus
from app.routers.auth import TermsVersion, request_info
from app.services import availability as availability_service
from app.services import checklists, consent, family, legal
from app.services import children as children_service
from app.services import search as search_service
from app.services.accounts import normalise_mobile
from app.services.storage import StorageClient, get_storage

Storage = Annotated[StorageClient, Depends(get_storage)]

router = APIRouter(prefix="/parent", tags=["parent"], dependencies=[Depends(require_role(Role.parent))])
Parent = Annotated[Profile, Depends(require_role(Role.parent))]


class ChecklistItem(BaseModel):
    key: str
    status: checklists.ItemStatus
    reason: str | None = None  # when rejected: why, in the admin's words


class Checklist(BaseModel):
    items: list[ChecklistItem]
    # Everything needed to book is done (birth certificates sent; they needn't be verified yet).
    finished: bool


def checklist_out(items: list[checklists.Item]) -> list[ChecklistItem]:
    return [ChecklistItem(key=item.key, status=item.status, reason=item.reason) for item in items]


@router.get("/checklist")
def get_checklist(parent: Parent, db: DbSession) -> Checklist:
    """What's left of "finish your profile" (CLAUDE.md 6.13)."""
    items = checklists.parent_checklist(db, parent)
    return Checklist(items=checklist_out(items), finished=checklists.parent_profile_finished(items))


class ConsentStatus(BaseModel):
    version: str  # the current version
    required_accepted: bool  # every required consent given, at the current version
    accepted_at: datetime | None  # when the last required one was given, if all are
    marketing: bool  # current opt-in state


class AcceptConsent(BaseModel):
    version: str  # the version the parent was shown
    marketing: bool  # whether they also ticked the optional marketing box
    # The Family Terms and privacy policy versions shown beside the consents and ticked (CLAUDE.md 7).
    accepted: list[TermsVersion] = Field(default_factory=list, max_length=5)


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
def accept_consent(body: AcceptConsent, request: Request, parent: Parent, db: DbSession) -> ConsentStatus:
    terms = [legal.Accepted(kind=item.kind, version=item.version) for item in body.accepted]
    return _status(consent.accept(db, parent.id, body.version, body.marketing, terms, request_info(request)))


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


# ---------- children (CLAUDE.md sections 6.4 and 8) ----------


class ChildIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    date_of_birth: date
    allergies: str | None = Field(default=None, max_length=1000)
    medical_notes: str | None = Field(default=None, max_length=1000)
    routines: str | None = Field(default=None, max_length=1000)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Please enter a name")
        return cleaned

    @field_validator("date_of_birth")
    @classmethod
    def _not_in_the_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("That date hasn't happened yet")
        return value

    @field_validator("allergies", "medical_notes", "routines")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return (" ".join(value.split()) or None) if value is not None else None


class ChildOut(BaseModel):
    id: uuid.UUID
    name: str
    date_of_birth: date
    allergies: str | None
    medical_notes: str | None
    routines: str | None
    verification_status: VerificationStatus
    rejection_reason: str | None  # why Pacify couldn't accept the birth certificate


def _child_out(child: Child) -> ChildOut:
    return ChildOut(
        id=child.id,
        name=child.name,
        date_of_birth=child.date_of_birth,
        allergies=child.allergies,
        medical_notes=child.medical_notes,
        routines=child.routines,
        verification_status=child.verification_status,
        rejection_reason=child.rejection_reason,
    )


@router.get("/children")
def get_children(parent: Parent, db: DbSession) -> list[ChildOut]:
    return [_child_out(child) for child in children_service.list_children(db, parent.id)]


@router.post("/children", status_code=201)
def post_child(body: ChildIn, parent: Parent, db: DbSession) -> ChildOut:
    child = children_service.add_child(
        db, parent.id, body.name, body.date_of_birth, body.allergies, body.medical_notes, body.routines
    )
    return _child_out(child)


@router.put("/children/{child_id}")
def put_child(child_id: uuid.UUID, body: ChildIn, parent: Parent, db: DbSession) -> ChildOut:
    child = children_service.update_child(
        db, parent.id, child_id, body.name, body.date_of_birth, body.allergies, body.medical_notes, body.routines
    )
    return _child_out(child)


@router.delete("/children/{child_id}", status_code=204)
def delete_child(child_id: uuid.UUID, parent: Parent, db: DbSession) -> None:
    children_service.remove_child(db, parent.id, child_id)


# ---------- finding sitters (CLAUDE.md 9 "Search and filters") ----------


class SitterSummary(BaseModel):
    """What parents see of a sitter. Never her pay, level pay, address, phone or email (CLAUDE.md 6.2)."""

    id: uuid.UUID
    full_name: str | None
    years_experience: int | None
    age_groups: list[str]
    languages: list[str]
    first_aid: bool
    avg_rating: float | None
    review_count: int
    distance_km: float | None  # straight line from the parent's home, to 0.1 km
    photo_url: str | None  # short-lived signed URL; live sitters only
    plan: SitterLevel  # the plan she works (her level), shown as a label; its price only when booking


class WeekHours(BaseModel):
    """A time she's usually free, every week (India time, whole hours; weekday 0 is Monday)."""

    weekday: int = Field(ge=0, le=6)
    start_hour: int = Field(ge=0, le=23)
    end_hour: int = Field(ge=1, le=24)


class SharedReference(BaseModel):
    name: str
    phone: str
    relationship: str


class SitterDetail(SitterSummary):
    bio: str | None
    week: list[WeekHours]  # her usual week, repeating
    days_off: list[date]  # days she isn't free within the booking window (the next two weeks)
    # Recharge sitters only, with her consent (CLAUDE.md 6.2).
    reference: SharedReference | None


def _photo_url(db: DbSession, storage: StorageClient, sitter_id: uuid.UUID) -> str | None:
    path = search_service.photo_path(db, sitter_id)
    if path is None:
        return None
    try:
        return storage.create_signed_view_url(path)
    except AppError:  # storage hiccup: show initials rather than fail the page
        return None


def _summary_fields(found: search_service.Found, photo_url: str | None) -> dict:
    profile, sitter = found.profile, found.sitter
    return {
        "id": profile.id,
        "full_name": profile.full_name,
        "years_experience": sitter.years_experience,
        "age_groups": sitter.age_groups,
        "languages": sitter.languages,
        "first_aid": sitter.first_aid,
        "avg_rating": float(sitter.avg_rating) if sitter.avg_rating is not None else None,
        "review_count": sitter.review_count,
        "distance_km": round(found.distance_km, 1) if found.distance_km is not None else None,
        "photo_url": photo_url,
        "plan": sitter.level,
    }


@router.get("/sitters")
def search_sitters(
    parent: Parent,
    db: DbSession,
    storage: Storage,
    plan: SitterLevel | None = None,
    day: Annotated[date | None, Query()] = None,
    starts_at: Annotated[AwareDatetime | None, Query()] = None,
    ends_at: Annotated[AwareDatetime | None, Query()] = None,
    min_rating: Annotated[Decimal | None, Query(ge=1, le=5)] = None,
    min_years: Annotated[int | None, Query(ge=0, le=60)] = None,
    language: Annotated[str | None, Query(max_length=40)] = None,
    first_aid: bool = False,
    sort: search_service.SortBy = search_service.SortBy.distance,
) -> list[SitterSummary]:
    """Every live sitter, or one plan's level. Parents browse once their profile is finished (CLAUDE.md 7)."""
    checklists.require_finished_parent_profile(db, parent)
    if (starts_at is None) != (ends_at is None):
        raise AppError(422, "time_incomplete", "Choose both a start and an end time")
    if starts_at is not None and ends_at is not None and ends_at <= starts_at:
        raise AppError(422, "time_order", "The end time must be after the start time")
    filters = search_service.Filters(
        plan=plan,
        day=day,
        starts_at=starts_at,
        ends_at=ends_at,
        min_rating=min_rating,
        min_years=min_years,
        language=language,
        first_aid=first_aid,
        sort=sort,
    )
    return [
        SitterSummary(**_summary_fields(found, _photo_url(db, storage, found.profile.id)))
        for found in search_service.search(db, parent, filters, datetime.now(UTC))
    ]


@router.get("/sitters/{sitter_id}")
def get_sitter(sitter_id: uuid.UUID, parent: Parent, db: DbSession, storage: Storage) -> SitterDetail:
    checklists.require_finished_parent_profile(db, parent)
    found = search_service.live_sitter(db, parent, sitter_id)
    now = datetime.now(UTC)
    today = availability_service.today_in_india(now)
    last_day = today + timedelta(days=availability_service.BOOK_AHEAD_DAYS - 1)
    shared = search_service.shared_reference(db, found.sitter)
    return SitterDetail(
        **_summary_fields(found, _photo_url(db, storage, sitter_id)),
        bio=found.sitter.bio,
        week=[WeekHours(**vars(hours)) for hours in availability_service.week(db, sitter_id)],
        days_off=[day for day in availability_service.days_off(db, sitter_id, today) if day <= last_day],
        reference=(
            SharedReference(name=shared.name, phone=shared.phone, relationship=shared.relationship) if shared else None
        ),
    )
