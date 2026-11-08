"""Parents finding sitters (CLAUDE.md 9 "Search and filters"): only live sitters of the chosen plan's
level, filtered and sorted by distance, rating or experience. Parents never see a sitter's pay."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import AvailabilitySlot, OnboardingStatus, Profile, ProfileStatus, Sitter, SitterLevel
from app.services import availability, geocoding


class SortBy(StrEnum):
    distance = "distance"
    rating = "rating"
    experience = "experience"


@dataclass(frozen=True)
class Filters:
    plan: SitterLevel  # a sitter works only her own level's plan (CLAUDE.md 6.2)
    starts_at: datetime | None = None  # with ends_at: she's free for the whole of this time
    ends_at: datetime | None = None
    min_rating: Decimal | None = None
    min_years: int | None = None
    language: str | None = None
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


def search(db: Session, parent: Profile, filters: Filters) -> list[Found]:
    query = select(Profile, Sitter).join(Sitter, Sitter.profile_id == Profile.id).where(_live())
    query = query.where(Sitter.level == filters.plan)
    if filters.starts_at is not None and filters.ends_at is not None:
        query = query.where(
            exists().where(
                AvailabilitySlot.sitter_id == Sitter.profile_id,
                AvailabilitySlot.starts_at <= filters.starts_at,
                AvailabilitySlot.ends_at >= filters.ends_at,
            )
        )
    if filters.min_rating is not None:
        query = query.where(Sitter.avg_rating >= filters.min_rating)
    if filters.min_years is not None:
        query = query.where(Sitter.years_experience >= filters.min_years)
    if filters.first_aid:
        query = query.where(Sitter.first_aid.is_(True))

    language = filters.language.strip().lower() if filters.language else None
    found = [
        Found(profile, sitter, geocoding.distance_km(_position(parent), _position(profile)))
        for profile, sitter in db.execute(query).all()
        if not language or language in (spoken.lower() for spoken in sitter.languages)
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


def free_times(db: Session, sitter_id: uuid.UUID, now: datetime) -> list[AvailabilitySlot]:
    return availability.upcoming(db, sitter_id, now)
