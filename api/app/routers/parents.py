"""The parent area. Every route here is for parents only (CLAUDE.md 9: wrong role gets 403)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime, BaseModel, Field, field_validator
from sqlalchemy import select

from app.auth import require_role
from app.deps import DbSession
from app.errors import AppError
from app.models import (
    AuthorisedAdult,
    Booking,
    BookingStatus,
    Child,
    EmergencyContact,
    IncidentKind,
    IssueTopic,
    Payment,
    PaymentKind,
    PaymentStatus,
    Profile,
    Role,
    SitterLevel,
    VerificationStatus,
)
from app.routers.auth import TermsVersion, request_info
from app.services import availability as availability_service
from app.services import booking_mail, cancellations, checklists, consent, family, legal, pricing
from app.services import bookings as bookings_service
from app.services import chat as chat_service
from app.services import checkin as checkin_service
from app.services import children as children_service
from app.services import email as email_service
from app.services import incidents as incidents_service
from app.services import overtime as overtime_service
from app.services import payments as payments_service
from app.services import reports as reports_service
from app.services import reviews as reviews_service
from app.services import search as search_service
from app.services import sitters as sitters_service
from app.services.accounts import normalise_mobile
from app.services.storage import StorageClient, get_storage
from app.settings import Settings, get_settings

Storage = Annotated[StorageClient, Depends(get_storage)]

router = APIRouter(prefix="/parent", tags=["parent"], dependencies=[Depends(require_role(Role.parent))])
Parent = Annotated[Profile, Depends(require_role(Role.parent))]


class ChecklistItem(BaseModel):
    key: str
    status: checklists.ItemStatus
    reason: str | None = None  # when rejected: why, in the admin's words
    note: str | None = None  # the exact next action, e.g. "1 child · certificate needed"


class Checklist(BaseModel):
    items: list[ChecklistItem]
    # Everything needed to book is done (birth certificates sent; they needn't be verified yet).
    finished: bool


def checklist_out(items: list[checklists.Item]) -> list[ChecklistItem]:
    return [ChecklistItem(key=item.key, status=item.status, reason=item.reason, note=item.note) for item in items]


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
    # One per family (Reuben, 2026-11-13; was two), not per child. Kept as a list so the API can grow.
    contacts: list[ContactIn] = Field(min_length=1, max_length=1)


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
    # Family data only after the parental consent (UX review 2026-11-13).
    consent.require_current_consent(db, parent.id)
    # An emergency contact is someone else to call: never the parent's own number.
    if parent.phone and any(contact.phone == parent.phone for contact in body.contacts):
        raise AppError(
            422,
            "emergency_contact_is_you",
            "An emergency contact needs a different number from yours",
            {"field": "phone"},
        )
    contacts = [(c.name, c.relationship, c.phone) for c in body.contacts]
    return [_contact_out(row) for row in family.set_emergency_contacts(db, parent.id, contacts)]


@router.get("/authorised-adults")
def get_authorised_adults(parent: Parent, db: DbSession) -> list[ContactOut]:
    return [_contact_out(row) for row in family.list_authorised_adults(db, parent.id)]


@router.post("/authorised-adults", status_code=201)
def post_authorised_adult(body: ContactIn, parent: Parent, db: DbSession) -> ContactOut:
    consent.require_current_consent(db, parent.id)
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
    rejection_reason: str | None  # why Pacifyco couldn't accept the birth certificate
    verified_at: datetime | None  # shown as "Verified 13 Nov" (UX review 2026-11-13)


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
        verified_at=child.verified_at if child.verification_status == VerificationStatus.approved else None,
    )


@router.get("/children")
def get_children(parent: Parent, db: DbSession) -> list[ChildOut]:
    return [_child_out(child) for child in children_service.list_children(db, parent.id)]


@router.post("/children", status_code=201)
def post_child(body: ChildIn, parent: Parent, db: DbSession) -> ChildOut:
    consent.require_current_consent(db, parent.id)  # children's data only after consent
    child = children_service.add_child(
        db, parent.id, body.name, body.date_of_birth, body.allergies, body.medical_notes, body.routines
    )
    return _child_out(child)


@router.put("/children/{child_id}")
def put_child(child_id: uuid.UUID, body: ChildIn, parent: Parent, db: DbSession) -> ChildOut:
    consent.require_current_consent(db, parent.id)
    child = children_service.update_child(
        db, parent.id, child_id, body.name, body.date_of_birth, body.allergies, body.medical_notes, body.routines
    )
    return _child_out(child)


@router.delete("/children/{child_id}", status_code=204)
def delete_child(child_id: uuid.UUID, parent: Parent, db: DbSession) -> None:
    children_service.remove_child(db, parent.id, child_id)


# ---------- finding sitters (CLAUDE.md 9 "Search and filters") ----------


class Price(BaseModel):
    """What the parent pays per hour with this sitter (her plan's price, CLAUDE.md 6.1). Parents see the
    rate, never the plan's name (Reuben, 2026-11-17)."""

    per_hour_paise: int  # for one child
    extra_child_paise: int  # added per hour for each extra child; 0 means the same for any number
    one_child_only: bool


def _price(plan: SitterLevel) -> Price:
    rate = pricing.RATES[plan]
    return Price(
        per_hour_paise=rate.first_child_paise,
        extra_child_paise=rate.extra_child_paise,
        one_child_only=rate.max_children == 1,
    )


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
    plan: SitterLevel  # the plan she works (her level); never shown to parents by name
    price: Price  # her plan's price per hour, shown on her card and profile
    # References are optional (2026-11-13): "References checked" only when one has been approved.
    references_checked: bool


class WeekHours(BaseModel):
    """A time she's usually free, every week (India time, whole hours; weekday 0 is Monday)."""

    weekday: int = Field(ge=0, le=6)
    start_hour: int = Field(ge=0, le=23)
    end_hour: int = Field(ge=1, le=24)


class SharedReference(BaseModel):
    # Never the referee's phone number (UX review 2026-11-13): parents contact sitters through Pacifyco.
    name: str
    relationship: str


def first_name(name: str | None) -> str | None:
    name = (name or "").strip()
    return name.split()[0] if name else None


class PublicReview(BaseModel):
    """A parent's review of a sitter, as shown on her profile: the parent's first name only."""

    rating: int
    body: str | None
    author_first_name: str | None
    created_at: datetime


def public_reviews(db, sitter_id: uuid.UUID) -> list[PublicReview]:
    return [
        PublicReview(
            rating=item.rating,
            body=item.body,
            author_first_name=first_name(item.author_name),
            created_at=item.created_at,
        )
        for item in reviews_service.about(db, sitter_id, limit=reviews_service.PUBLIC_LIMIT)
    ]


class SitterDetail(SitterSummary):
    bio: str | None
    # Shown to parents on her profile page (Reuben, 2026-11-16).
    university: str | None
    semester: int | None
    week: list[WeekHours]  # her usual week, repeating
    days_off: list[date]  # days she isn't free within the booking window (the next two weeks)
    # Recharge sitters only, with her consent (CLAUDE.md 6.2).
    reference: SharedReference | None
    joined_at: datetime  # shown as "Joined Nov 2026" (UX review 2026-11-13)
    # Families' reviews of her, newest first (Reuben, 2026-11-22): the parent's first name only.
    reviews: list[PublicReview]


def _photo_url(db: DbSession, storage: StorageClient, sitter_id: uuid.UUID) -> str | None:
    path = search_service.photo_path(db, sitter_id)
    if path is None:
        return None
    try:
        return storage.create_signed_view_url(path)
    except AppError:  # storage hiccup: show initials rather than fail the page
        return None


def _summary_fields(db: DbSession, found: search_service.Found, photo_url: str | None) -> dict:
    profile, sitter = found.profile, found.sitter
    return {
        "id": profile.id,
        "full_name": profile.full_name,
        "years_experience": sitter.years_experience,
        "age_groups": sitters_service.known(sitter.age_groups, sitters_service.AGE_GROUPS),
        "languages": sitters_service.known(sitter.languages, sitters_service.LANGUAGES),
        "first_aid": sitter.first_aid,
        "avg_rating": float(sitter.avg_rating) if sitter.avg_rating is not None else None,
        "review_count": sitter.review_count,
        "distance_km": round(found.distance_km, 1) if found.distance_km is not None else None,
        "photo_url": photo_url,
        "plan": sitter.level,
        "price": _price(sitter.level),
        "references_checked": search_service.has_approved_reference(db, sitter.profile_id),
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
    # Repeat it for several: ?language=English&language=Tamil finds sitters who speak any of them.
    language: Annotated[list[str], Query(max_length=10)] = [],  # noqa: B006 (FastAPI copies defaults)
    first_aid: bool = False,
    part: Annotated[Literal["morning", "afternoon", "evening", "night"] | None, Query()] = None,
    sort: search_service.SortBy = search_service.SortBy.distance,
) -> list[SitterSummary]:
    """Every live sitter, or one plan's level. Parents browse once their profile is finished (CLAUDE.md 7)."""
    checklists.require_finished_parent_profile(db, parent)
    if part is not None and day is None:
        raise AppError(422, "day_needed", "Choose a day as well as a time of day")
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
        languages=tuple(item[:40] for item in language),
        part=part,
        first_aid=first_aid,
        sort=sort,
    )
    return [
        SitterSummary(**_summary_fields(db, found, _photo_url(db, storage, found.profile.id)))
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
        **_summary_fields(db, found, _photo_url(db, storage, sitter_id)),
        bio=found.sitter.bio,
        university=found.sitter.university,
        semester=found.sitter.semester,
        week=[WeekHours(**vars(hours)) for hours in availability_service.week(db, sitter_id)],
        days_off=[day for day in availability_service.days_off(db, sitter_id, today) if day <= last_day],
        reference=(SharedReference(name=shared.name, relationship=shared.relationship) if shared else None),
        joined_at=found.profile.created_at,
        reviews=public_reviews(db, sitter_id),
    )


# ---------- booking a sitter (CLAUDE.md 6.1 and 6.4; phase 6 "Book this sitter") ----------


class BookableTime(BaseModel):
    """A stretch she's free that a booking can start in (whole hours, already cut to her plan's latest
    end and starting 4+ hours from now)."""

    starts_at: datetime
    ends_at: datetime


class BookingOptions(BaseModel):
    price: Price
    bath_time_allowed: bool
    outings_allowed: bool  # Recharge only (6.1)
    times: list[BookableTime]
    # No earlier booking with her: the booking page asks for a 1-hour first booking at home (6.3).
    first_booking: bool
    # Unpaid charges: no new booking until they're paid (6.4).
    owed_paise: int


@router.get("/sitters/{sitter_id}/booking-options")
def get_booking_options(sitter_id: uuid.UUID, parent: Parent, db: DbSession) -> BookingOptions:
    # Money owed doesn't stop the page: it shows what's owed instead of the form (`owed_paise`).
    bookings_service.require_terms_then_profile(db, parent)
    found = search_service.live_sitter(db, parent, sitter_id)
    plan = found.sitter.level
    times = bookings_service.bookable_times(db, found.sitter, datetime.now(UTC))
    return BookingOptions(
        price=_price(plan),
        bath_time_allowed=bookings_service.BATH_TIME[plan],
        outings_allowed=bookings_service.OUTINGS[plan],
        times=[BookableTime(starts_at=item.starts_at, ends_at=item.ends_at) for item in times],
        first_booking=bookings_service.first_booking_with(db, parent.id, sitter_id),
        owed_paise=bookings_service.amount_owed(db, parent.id),
    )


class BookingIn(BaseModel):
    sitter_id: uuid.UUID
    starts_at: AwareDatetime
    hours: int = Field(ge=1, le=24, strict=True)  # whole hours only (decided 2026-11-03)
    child_ids: list[uuid.UUID] = Field(min_length=1, max_length=bookings_service.MAX_CHILDREN)
    bath_time: bool = False
    cameras_on: bool  # required: the parent must say (6.4)
    camera_locations: str | None = Field(default=None, max_length=500)
    # Recharge only: where the family will be out (Reuben, 2026-11-21); the address goes in the chat.
    outing_where: str | None = Field(default=None, max_length=300)


class PayByUpi(BaseModel):
    """Where and how to pay (6.1): Pacifyco's UPI ID and a `upi://pay` link (the page shows it as a QR
    code too)."""

    upi_id: str
    payee_name: str
    amount_paise: int
    note: str
    upi_link: str


class PaymentOut(BaseModel):
    """The latest payment the parent sent for this booking."""

    status: str
    upi_reference: str | None
    sent_at: datetime
    rejection_reason: str | None


class ReportOut(BaseModel):
    """A report during the booking (6.5): the parent wasn't home, or the sitter didn't come."""

    id: uuid.UUID
    kind: str  # parent_absent | sitter_no_show | only_man_home | child_under_age | sitter_unsafe
    status: str  # open | confirmed | dismissed
    reported_at: datetime
    responded_at: datetime | None  # parent not home: a parent responded, so she waits
    can_leave_at: datetime | None  # parent not home: she may leave from then, if no one responds
    decision_note: str | None


def report_out(db, booking_id: uuid.UUID) -> ReportOut | None:
    report = reports_service.for_booking(db, booking_id)
    if report is None:
        return None
    return ReportOut(
        id=report.id,
        kind=report.kind.value,
        status=report.status.value,
        reported_at=report.reported_at,
        responded_at=report.responded_at,
        can_leave_at=reports_service.can_leave_at(report),
        decision_note=report.decision_note,
    )


class OvertimeRequestOut(BaseModel):
    """The booking's latest overtime request (6.8): nothing is charged here either way."""

    id: uuid.UUID
    hours: int
    status: str  # pending | accepted | declined
    requested_at: datetime
    decided_at: datetime | None


def overtime_out(db, booking_id: uuid.UUID) -> OvertimeRequestOut | None:
    found = overtime_service.for_booking(db, booking_id)
    if found is None:
        return None
    return OvertimeRequestOut(
        id=found.id,
        hours=found.requested_hours,
        status=found.status.value,
        requested_at=found.requested_at,
        decided_at=found.decided_at,
    )


class IncidentOut(BaseModel):
    """The booking's latest Emergency report (6.9)."""

    kind: str
    status: str  # open | acknowledged | resolved
    created_at: datetime


def incident_out(db, booking_id: uuid.UUID) -> IncidentOut | None:
    incident = incidents_service.latest_incident(db, booking_id)
    if incident is None:
        return None
    return IncidentOut(kind=incident.kind.value, status=incident.status.value, created_at=incident.created_at)


class EmergencyIn(BaseModel):
    kind: IncidentKind
    note: str | None = Field(default=None, max_length=1000)


class IssueIn(BaseModel):
    topic: IssueTopic
    note: str | None = Field(default=None, max_length=1000)


class IssueOut(BaseModel):
    id: uuid.UUID
    topic: str
    status: str


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    body: str | None = Field(default=None, max_length=reviews_service.BODY_MAX)


class MyReviewOut(BaseModel):
    rating: int
    body: str | None
    created_at: datetime


class ReviewState(BaseModel):
    """The person's own review of this booking (6.11): what they left, or whether they can leave one now
    and until when. Never the other person's review of them."""

    mine: MyReviewOut | None
    can_review: bool
    open_until: datetime | None  # only while they can


def review_state(db, booking, author_id: uuid.UUID) -> ReviewState:
    mine = reviews_service.mine(db, booking.id, author_id)
    can = mine is None and reviews_service.can_review(db, booking, author_id, datetime.now(UTC))
    return ReviewState(
        mine=MyReviewOut(rating=mine.rating, body=mine.body, created_at=mine.created_at) if mine else None,
        can_review=can,
        open_until=reviews_service.open_until(booking) if can else None,
    )


class BookingOut(BaseModel):
    """The parent's view of a booking: never the plan's name or the sitter's pay (6.1)."""

    id: uuid.UUID
    sitter_id: uuid.UUID
    sitter_name: str | None
    starts_at: datetime
    ends_at: datetime
    hours: int
    children: list[str]
    price_paise: int
    bath_time: bool
    cameras_on: bool
    camera_locations: str | None
    outing_where: str | None  # an outing: where the family will be (Recharge only)
    outings_allowed: bool  # the plan allows outings (Recharge)
    status: str
    pay_by: datetime  # unpaid bookings are cancelled at this time (6.1)
    # A request (6.4): whether the sitter can see it yet (every child verified), and when it lapses if she
    # hasn't answered.
    seen_by_sitter: bool
    answer_by: datetime | None
    # Only while the booking waits for payment and Pacifyco's UPI ID is set.
    pay_by_upi: PayByUpi | None
    payment: PaymentOut | None
    report: ReportOut | None
    # The Emergency and Issues buttons: from the start until 1 hour after the end or check-out (6.9).
    buttons_open: bool
    incident: IncidentOut | None
    checked_in_at: datetime | None  # (6.7)
    checked_out_at: datetime | None
    overtime: OvertimeRequestOut | None  # (6.8)
    review: ReviewState  # the parent's review of the sitter (6.11)


AppSettings = Annotated[Settings, Depends(get_settings)]
Mailer = Annotated[email_service.EmailClient, Depends(email_service.get_email)]


def _booking_out(db: DbSession, booking, settings: Settings) -> BookingOut:
    home = bookings_service.home_info(db, booking.id)
    sitter = db.get(Profile, booking.sitter_id)
    instructions = (
        payments_service.payment_instructions(settings.pacify_upi_id, booking)
        if booking.status == BookingStatus.pending_payment
        else None
    )
    payment = payments_service.latest_booking_payment(db, booking.id)
    return BookingOut(
        id=booking.id,
        sitter_id=booking.sitter_id,
        sitter_name=sitter.full_name if sitter else None,
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
        hours=booking.units,
        children=bookings_service.child_names(db, booking.id),
        price_paise=booking.price_paise,
        bath_time=booking.bath_time,
        cameras_on=home.cameras_on if home else False,
        camera_locations=home.camera_locations if home else None,
        outing_where=home.outing_where if home else None,
        outings_allowed=bookings_service.OUTINGS[booking.plan],
        status=booking.status.value,
        pay_by=bookings_service.pay_by(booking),
        seen_by_sitter=booking.request_visible_at is not None,
        answer_by=bookings_service.answer_by(booking) if booking.status == BookingStatus.requested else None,
        pay_by_upi=PayByUpi(**vars(instructions)) if instructions else None,
        payment=PaymentOut(
            status=payment.status.value,
            upi_reference=payment.upi_reference,
            sent_at=payment.created_at,
            rejection_reason=payment.rejection_reason,
        )
        if payment
        else None,
        report=report_out(db, booking.id),
        buttons_open=incidents_service.buttons_open(booking, datetime.now(UTC)),
        incident=incident_out(db, booking.id),
        checked_in_at=booking.checked_in_at,
        checked_out_at=booking.checked_out_at,
        overtime=overtime_out(db, booking.id),
        review=review_state(db, booking, booking.parent_id),
    )


@router.post("/bookings", status_code=201)
def post_booking(body: BookingIn, parent: Parent, db: DbSession, settings: AppSettings, mailer: Mailer) -> BookingOut:
    """A request to the sitter (6.4). She's told now if every child on it is verified; otherwise once
    they are."""
    new = bookings_service.NewBooking(**body.model_dump())
    booking = bookings_service.create(db, parent, new, datetime.now(UTC))
    if booking.request_visible_at is not None:
        booking_mail.tell_sitter(db, mailer, settings, booking.id)
    return _booking_out(db, booking, settings)


class BookingListItem(BaseModel):
    """A line in the parent's bookings list: never the plan's name or the sitter's pay (6.1)."""

    id: uuid.UUID
    sitter_id: uuid.UUID
    sitter_name: str | None
    starts_at: datetime
    ends_at: datetime
    hours: int
    children: list[str]
    price_paise: int
    status: str
    pay_by: datetime
    # A UPI reference sent and waiting for Pacifyco to check it.
    payment_sent: bool


class BookingList(BaseModel):
    upcoming: list[BookingListItem]  # soonest first
    past: list[BookingListItem]  # ended or cancelled, most recent first


@router.get("/bookings")
def get_bookings(parent: Parent, db: DbSession) -> BookingList:
    """Every booking the parent has made (phase 7 "Parent booking lists")."""
    now = datetime.now(UTC)
    # Overdue ones are cancelled now, not at the next job run (as when one booking is opened).
    closed = [
        bookings_service.lapse_requests(db, now, parent_id=parent.id),
        bookings_service.cancel_unpaid(db, now, parent_id=parent.id),
        bookings_service.cancel_unverified(db, now, parent_id=parent.id),
    ]
    if any(closed):
        db.commit()
    upcoming, past = bookings_service.parents_bookings(db, parent.id, now)
    everything = [*upcoming, *past]
    ids = [item.id for item in everything]
    names = bookings_service.child_names_for(db, ids)
    sitters = {
        row.id: row.full_name
        for row in db.execute(
            select(Profile.id, Profile.full_name).where(Profile.id.in_({item.sitter_id for item in everything}))
        )
    }
    sent = set(
        db.scalars(
            select(Payment.booking_id).where(
                Payment.booking_id.in_(ids),
                Payment.kind == PaymentKind.booking,
                Payment.status == PaymentStatus.pending,
            )
        )
    )

    def item(booking) -> BookingListItem:
        return BookingListItem(
            id=booking.id,
            sitter_id=booking.sitter_id,
            sitter_name=sitters.get(booking.sitter_id),
            starts_at=booking.starts_at,
            ends_at=booking.ends_at,
            hours=booking.units,
            children=names[booking.id],
            price_paise=booking.price_paise,
            status=booking.status.value,
            pay_by=bookings_service.pay_by(booking),
            payment_sent=booking.id in sent,
        )

    return BookingList(upcoming=[item(b) for b in upcoming], past=[item(b) for b in past])


@router.get("/bookings/{booking_id}")
def get_booking(booking_id: uuid.UUID, parent: Parent, db: DbSession, settings: AppSettings) -> BookingOut:
    booking = bookings_service.parents_booking(db, parent.id, booking_id)
    # A request not answered in time, past its payment deadline with nothing sent, or started with a child
    # still unverified: closed now, not at the next job run. (The parent sees it here, so no email.)
    now = datetime.now(UTC)
    if (
        bookings_service.lapse_requests(db, now, booking_id=booking.id)
        or bookings_service.cancel_unpaid(db, now, booking.id)
        or bookings_service.cancel_unverified(db, now, booking.id)
    ):
        db.commit()
        db.refresh(booking)
    return _booking_out(db, booking, settings)


class CodeOut(BaseModel):
    code: str


@router.get("/bookings/{booking_id}/check-in-code")
def get_check_in_code(booking_id: uuid.UUID, parent: Parent, db: DbSession, settings: AppSettings) -> CodeOut:
    """Only on the day of the booking, while it's confirmed (6.7)."""
    code = checkin_service.check_in_code(db, parent.id, booking_id, settings.field_encryption_key, datetime.now(UTC))
    return CodeOut(code=code)


@router.get("/bookings/{booking_id}/check-out-code")
def get_check_out_code(booking_id: uuid.UUID, parent: Parent, db: DbSession, settings: AppSettings) -> CodeOut:
    """Only once the sitter has checked in (6.7)."""
    code = checkin_service.check_out_code(db, parent.id, booking_id, settings.field_encryption_key)
    return CodeOut(code=code)


class OvertimeRequestIn(BaseModel):
    hours: int = Field(ge=1, le=24)


@router.post("/bookings/{booking_id}/overtime", status_code=201)
def request_overtime(
    booking_id: uuid.UUID, body: OvertimeRequestIn, parent: Parent, db: DbSession, mailer: Mailer, settings: AppSettings
) -> BookingOut:
    """Asks the sitter for extra whole hours, once the booking has started (6.8). Nothing is charged
    now; it's worked out at check-out."""
    overtime_service.request(db, parent.id, booking_id, body.hours, datetime.now(UTC))
    booking_mail.tell_sitter_overtime_requested(db, mailer, settings, booking_id, body.hours)
    return _booking_out(db, bookings_service.parents_booking(db, parent.id, booking_id), settings)


@router.post("/bookings/{booking_id}/emergency", status_code=201)
def parent_emergency(
    booking_id: uuid.UUID, body: EmergencyIn, parent: Parent, db: DbSession, settings: AppSettings, mailer: Mailer
) -> BookingOut:
    """Emergency, theft or abuse (6.9): every admin is emailed at once; theft or abuse suspends the sitter."""
    incident = incidents_service.raise_emergency(db, parent, booking_id, body.kind, body.note, datetime.now(UTC))
    booking_mail.tell_incident(db, mailer, settings, incident)
    return _booking_out(db, bookings_service.parents_booking(db, parent.id, booking_id), settings)


@router.post("/bookings/{booking_id}/issues", status_code=201)
def parent_issue(
    booking_id: uuid.UUID, body: IssueIn, parent: Parent, db: DbSession, settings: AppSettings, mailer: Mailer
) -> IssueOut:
    """A non-emergency issue, linked to the booking, for admins (6.9)."""
    complaint = incidents_service.raise_issue(db, parent, booking_id, body.topic, body.note, datetime.now(UTC))
    booking_mail.tell_issue(db, mailer, settings, complaint, incidents_service.TOPIC_WORDS[body.topic])
    return IssueOut(id=complaint.id, topic=body.topic.value, status=complaint.status.value)


@router.post("/bookings/{booking_id}/arrived")
def parent_arrived(booking_id: uuid.UUID, parent: Parent, db: DbSession, settings: AppSettings) -> BookingOut:
    """The sitter said no one was home; the parent says they've arrived: she waits for them (6.5)."""
    report = reports_service.parents_open_absence(db, parent.id, booking_id)
    reports_service.parent_responded(db, parent.id, report.id, datetime.now(UTC))
    return _booking_out(db, bookings_service.parents_booking(db, parent.id, booking_id), settings)


@router.post("/bookings/{booking_id}/no-show", status_code=201)
def report_no_show(
    booking_id: uuid.UUID, parent: Parent, db: DbSession, settings: AppSettings, mailer: Mailer
) -> BookingOut:
    """The sitter didn't come: from 30 minutes after the start. An admin confirms it (6.5)."""
    report = reports_service.sitter_no_show(db, parent.id, booking_id, datetime.now(UTC))
    booking_mail.tell_reported(db, mailer, settings, report)
    return _booking_out(db, bookings_service.parents_booking(db, parent.id, booking_id), settings)


class OutingIn(BaseModel):
    outing_where: str | None = Field(default=None, max_length=300)  # None or blank: no outing


@router.put("/bookings/{booking_id}/outing")
def set_outing(
    booking_id: uuid.UUID, body: OutingIn, parent: Parent, db: DbSession, settings: AppSettings, mailer: Mailer
) -> BookingOut:
    """Add, change or remove an outing (Recharge only) until the start. A sitter who has accepted is told."""
    booking, tell = bookings_service.set_outing(db, parent.id, booking_id, body.outing_where, datetime.now(UTC))
    if tell:
        home = bookings_service.home_info(db, booking.id)
        booking_mail.tell_outing_changed(db, mailer, settings, booking.id, home.outing_where if home else None)
    return _booking_out(db, booking, settings)


@router.post("/bookings/{booking_id}/review", status_code=201)
def post_review(
    booking_id: uuid.UUID, body: ReviewIn, parent: Parent, db: DbSession, settings: AppSettings, mailer: Mailer
) -> BookingOut:
    """The parent's rating and review of the sitter, once, within 14 days of the end (6.11)."""
    left = reviews_service.leave(db, parent, booking_id, body.rating, body.body, datetime.now(UTC))
    if left.flag is not None:
        booking_mail.tell_admins_rating_flag(db, mailer, settings, left.flag)
    return _booking_out(db, bookings_service.parents_booking(db, parent.id, booking_id), settings)


@router.post("/bookings/{booking_id}/cancel")
def cancel_booking(
    booking_id: uuid.UUID, parent: Parent, db: DbSession, settings: AppSettings, mailer: Mailer
) -> BookingOut:
    """3 hours or more before the start: refunded in full; less: the whole booking is charged (6.5)."""
    done = cancellations.by_parent(db, parent.id, booking_id, datetime.now(UTC))
    if done.was_accepted:
        booking_mail.tell_sitter_cancelled_by_family(db, mailer, settings, done.booking.id)
    return _booking_out(db, done.booking, settings)


class ChargeOut(BaseModel):
    """A charge the parent owes (6.5; overtime in phase 8) and how to pay it by UPI."""

    id: uuid.UUID
    kind: str  # cancellation_charge | overtime
    amount_paise: int
    status: str  # pending (owed) | confirmed (paid) | waived (let go by Pacifyco)
    upi_reference: str | None  # sent and waiting for Pacifyco to check it
    rejection_reason: str | None  # the last reference couldn't be confirmed
    waive_reason: str | None  # why Pacifyco waived it
    booking_id: uuid.UUID
    booking_starts_at: datetime
    sitter_name: str | None
    pay_by_upi: PayByUpi | None  # only while it's owed, nothing sent, and the UPI ID is set


def _charge_out(db: DbSession, charge, settings: Settings) -> ChargeOut:
    booking = db.get(Booking, charge.booking_id)
    assert booking is not None
    sitter = db.get(Profile, booking.sitter_id)
    owed = charge.status == PaymentStatus.pending and charge.upi_reference is None
    instructions = payments_service.charge_instructions(settings.pacify_upi_id, charge) if owed else None
    return ChargeOut(
        id=charge.id,
        kind=charge.kind.value,
        amount_paise=charge.amount_paise,
        status=charge.status.value,
        upi_reference=charge.upi_reference,
        rejection_reason=charge.rejection_reason if charge.status == PaymentStatus.pending else None,
        waive_reason=charge.waive_reason,
        booking_id=booking.id,
        booking_starts_at=booking.starts_at,
        sitter_name=sitter.full_name if sitter else None,
        pay_by_upi=PayByUpi(**vars(instructions)) if instructions else None,
    )


@router.get("/payments/{payment_id}")
def get_charge(payment_id: uuid.UUID, parent: Parent, db: DbSession, settings: AppSettings) -> ChargeOut:
    return _charge_out(db, payments_service.parents_charge(db, parent.id, payment_id), settings)


@router.post("/payments/{payment_id}/payment", status_code=201)
def pay_charge(
    payment_id: uuid.UUID, body: UpiReferenceIn, parent: Parent, db: DbSession, settings: AppSettings
) -> ChargeOut:
    """The parent has paid a charge by UPI: the reference waits for an admin to check it."""
    charge = payments_service.submit_charge_reference(db, parent, payment_id, body.upi_reference, datetime.now(UTC))
    return _charge_out(db, charge, settings)


class UpiReferenceIn(BaseModel):
    upi_reference: str = Field(max_length=40)


@router.post("/bookings/{booking_id}/payment", status_code=201)
def post_booking_payment(
    booking_id: uuid.UUID, body: UpiReferenceIn, parent: Parent, db: DbSession, settings: AppSettings
) -> BookingOut:
    """The parent has paid by UPI: record the reference for an admin to check (6.1)."""
    payments_service.submit_upi_reference(db, parent, booking_id, body.upi_reference, datetime.now(UTC))
    return _booking_out(db, bookings_service.parents_booking(db, parent.id, booking_id), settings)


# ---------- the parent's payments (CLAUDE.md 6.1; phase 6 "Parent payment history") ----------


class PaymentHistoryItem(BaseModel):
    """One payment, charge or refund. Amounts are positive; `kind` says which way the money went."""

    id: uuid.UUID
    kind: str  # booking | overtime | refund | cancellation_charge
    amount_paise: int
    status: str  # pending | confirmed | rejected | waived (a charge Pacifyco let go)
    upi_reference: str | None
    transfer_reference: str | None  # a refund's
    rejection_reason: str | None
    waive_reason: str | None
    created_at: datetime
    decided_at: datetime | None
    booking_id: uuid.UUID
    booking_starts_at: datetime
    sitter_name: str | None


class PaymentHistory(BaseModel):
    owed_paise: int
    payments: list[PaymentHistoryItem]


@router.get("/payments")
def get_payments(parent: Parent, db: DbSession) -> PaymentHistory:
    return PaymentHistory(
        owed_paise=bookings_service.amount_owed(db, parent.id),
        payments=[
            PaymentHistoryItem(
                id=item.payment.id,
                kind=item.payment.kind.value,
                amount_paise=abs(item.payment.amount_paise),
                status=item.payment.status.value,
                upi_reference=item.payment.upi_reference,
                transfer_reference=item.payment.transfer_reference,
                rejection_reason=item.payment.rejection_reason,
                waive_reason=item.payment.waive_reason,
                created_at=item.payment.created_at,
                decided_at=item.payment.confirmed_at,
                booking_id=item.booking.id,
                booking_starts_at=item.booking.starts_at,
                sitter_name=item.sitter_name,
            )
            for item in payments_service.history(db, parent.id)
        ],
    )


# ---------- chat (CLAUDE.md 6.11) ----------


class MessageOut(BaseModel):
    id: uuid.UUID
    from_me: bool
    body: str
    created_at: datetime


class ChatOut(BaseModel):
    """One conversation. The app asks again every 10 seconds while it's open, with `after` set to the last
    message's time, to get only new ones."""

    other_id: uuid.UUID
    other_name: str | None  # first name
    can_send: bool  # while they have a booking now or to come, and 24 hours after the last one
    messages: list[MessageOut]


class ChatSummaryOut(BaseModel):
    other_id: uuid.UUID
    other_name: str | None
    last_body: str | None
    last_at: datetime | None
    last_from_me: bool
    can_send: bool


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


def _first(name: str | None) -> str | None:
    name = (name or "").strip()
    return name.split()[0] if name else None


def chat_out(db, person, other_id: uuid.UUID, after: datetime | None) -> ChatOut:
    found = chat_service.read(db, person, other_id, datetime.now(UTC), after)
    other = db.get(Profile, other_id)
    return ChatOut(
        other_id=other_id,
        other_name=_first(other.full_name if other else None),
        can_send=found.can_send,
        messages=[
            MessageOut(id=m.id, from_me=m.sender_id == person.id, body=m.body, created_at=m.created_at)
            for m in found.messages
        ],
    )


def chat_summaries(db, person) -> list[ChatSummaryOut]:
    return [
        ChatSummaryOut(
            other_id=item.other_id,
            other_name=_first(item.other_name),
            last_body=item.last_body,
            last_at=item.last_at,
            last_from_me=item.last_from_me,
            can_send=item.can_send,
        )
        for item in chat_service.conversations(db, person, datetime.now(UTC))
    ]


@router.get("/chats")
def get_chats(parent: Parent, db: DbSession) -> list[ChatSummaryOut]:
    return chat_summaries(db, parent)


@router.get("/chats/{sitter_id}")
def get_chat(sitter_id: uuid.UUID, parent: Parent, db: DbSession, after: AwareDatetime | None = None) -> ChatOut:
    return chat_out(db, parent, sitter_id, after)


@router.post("/chats/{sitter_id}", status_code=201)
def send_message(sitter_id: uuid.UUID, body: MessageIn, parent: Parent, db: DbSession) -> ChatOut:
    chat_service.send(db, parent, sitter_id, body.body, datetime.now(UTC))
    return chat_out(db, parent, sitter_id, None)
