"""Parents finding sitters (CLAUDE.md 9 "Search and filters"): every live sitter, or only one plan's
level, filtered and sorted by distance, rating or experience. Parents never see a sitter's pay.
(Decided 2026-11-09: the parent's page lists every live sitter and filters by day and language.)"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import (
    Document,
    DocumentStatus,
    DocumentType,
    OnboardingStatus,
    Profile,
    ProfileStatus,
    Reference,
    Sitter,
    SitterLevel,
    VerificationStatus,
)
from app.services import availability, geocoding


class SortBy(StrEnum):
    distance = "distance"
    rating = "rating"
    experience = "experience"


@dataclass(frozen=True)
class Filters:
    plan: SitterLevel | None = None  # None: every level. A sitter works only her own level's plan (6.2)
    day: date | None = None  # she has free time left on this day (India time), from her weekly hours
    starts_at: datetime | None = None  # with ends_at: she's free for the whole of this time
    ends_at: datetime | None = None
    min_rating: Decimal | None = None
    min_years: int | None = None
    # Speaks any of these (several can be chosen, Reuben 2026-11-13); empty means any language.
    languages: tuple[str, ...] = ()
    part: str | None = None  # a part of the day (availability.PARTS_OF_DAY), on `day`
    first_aid: bool = False
    sort: SortBy = SortBy.distance


@dataclass(frozen=True)
class Found:
    profile: Profile
    sitter: Sitter
    distance_km: float | None


def _live():
    """Same rule as verification.is_live, as SQL. Strikes (phase 9) will also hide a blocked sitter."""
    return (
        (Profile.status == ProfileStatus.active)
        & (Sitter.onboarding_status == OnboardingStatus.approved)
        & Sitter.level.is_not(None)
    )


def _position(profile: Profile) -> tuple[Decimal | None, Decimal | None]:
    return profile.lat, profile.lng


def search(db: Session, parent: Profile, filters: Filters, now: datetime) -> list[Found]:
    query = select(Profile, Sitter).join(Sitter, Sitter.profile_id == Profile.id).where(_live())
    if filters.plan is not None:
        query = query.where(Sitter.level == filters.plan)
    if filters.min_rating is not None:
        query = query.where(Sitter.avg_rating >= filters.min_rating)
    if filters.min_years is not None:
        query = query.where(Sitter.years_experience >= filters.min_years)
    if filters.first_aid:
        query = query.where(Sitter.first_aid.is_(True))

    wanted = {language.strip().lower() for language in filters.languages if language.strip()}
    rows = [
        (profile, sitter)
        for profile, sitter in db.execute(query).all()
        if not wanted or wanted & {spoken.lower() for spoken in sitter.languages}
    ]
    # Free times come from each sitter's weekly hours and days off (worked out, not stored).
    if filters.day is not None or (filters.starts_at is not None and filters.ends_at is not None):
        times = availability.free_times_for(db, [profile.id for profile, _ in rows], now)
        if filters.day is not None and filters.part is not None:
            rows = [
                row for row in rows if availability.has_time_in_part(times[row[0].id], filters.day, filters.part, now)
            ]
        elif filters.day is not None:
            rows = [row for row in rows if availability.has_time_on(times[row[0].id], filters.day, now)]
        if filters.starts_at is not None and filters.ends_at is not None:
            rows = [row for row in rows if availability.is_free(times[row[0].id], filters.starts_at, filters.ends_at)]
    found = [
        Found(profile, sitter, geocoding.distance_km(_position(parent), _position(profile))) for profile, sitter in rows
    ]

    # Unknowns (no position, no rating yet) go last.
    if filters.sort == SortBy.distance:
        found.sort(key=lambda item: (item.distance_km is None, item.distance_km or 0))
    elif filters.sort == SortBy.rating:
        found.sort(key=lambda item: (item.sitter.avg_rating is None, -(item.sitter.avg_rating or 0)))
    else:
        found.sort(key=lambda item: -(item.sitter.years_experience or 0))
    return found


def live_sitter(db: Session, parent: Profile, sitter_id: uuid.UUID) -> Found:
    """One live sitter's profile. Anyone else is "not found", so parents can't probe for sitters who
    aren't live."""
    row = db.execute(
        select(Profile, Sitter).join(Sitter, Sitter.profile_id == Profile.id).where(Profile.id == sitter_id, _live())
    ).first()
    if row is None:
        raise AppError(404, "not_found", "That sitter isn't available")
    profile, sitter = row
    return Found(profile, sitter, geocoding.distance_km(_position(parent), _position(profile)))


def has_approved_reference(db: Session, sitter_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(Reference.id)
            .where(
                Reference.sitter_id == sitter_id,
                Reference.outcome == VerificationStatus.approved,
                Reference.removed_at.is_(None),
            )
            .limit(1)
        )
        is not None
    )


def shared_reference(db: Session, sitter: Sitter) -> Reference | None:
    """At Recharge level, with her consent, one reference an admin approved is shown to parents
    (CLAUDE.md 6.2). Nothing otherwise."""
    if sitter.level != SitterLevel.recharge or not sitter.reference_shared_consent:
        return None
    return db.scalar(
        select(Reference)
        .where(
            Reference.sitter_id == sitter.profile_id,
            Reference.outcome == VerificationStatus.approved,
            Reference.removed_at.is_(None),
        )
        .order_by(Reference.name)
        .limit(1)
    )


def photo_path(db: Session, sitter_id: uuid.UUID) -> str | None:
    """Her latest profile photo. Shown to parents only while she's live, through a short-lived signed
    URL (CLAUDE.md 5; the one exception to admin-only files, decided 2026-11-09)."""
    return db.scalar(
        select(Document.storage_path)
        .where(
            Document.owner_profile_id == sitter_id,
            Document.type == DocumentType.photo,
            Document.status == DocumentStatus.uploaded,
            Document.deleted_at.is_(None),
        )
        .order_by(Document.created_at.desc())
        .limit(1)
    )
