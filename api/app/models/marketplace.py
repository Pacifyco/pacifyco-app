"""The marketplace (CLAUDE.md 8, phase 5): sitters' weekly hours and days off, and cached geocoding results."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Numeric, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import created_at, uuid_pk


class WeeklyHours(Base):
    """A time a sitter is usually free on one weekday, repeating every week (decided 2026-11-09,
    replaces dated free times). Whole hours in India time; weekday 0 is Monday."""

    __tablename__ = "weekly_hours"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("start_hour BETWEEN 0 AND 23", name="start_hour_range"),
        CheckConstraint("end_hour BETWEEN 1 AND 24", name="end_hour_range"),
        CheckConstraint("end_hour > start_hour", name="ends_after_start"),
        Index("ix_weekly_hours_sitter_id", "sitter_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    sitter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sitters.profile_id", ondelete="CASCADE"))
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start_hour: Mapped[int] = mapped_column(SmallInteger)
    end_hour: Mapped[int] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = created_at()


class DayOff(Base):
    """A date a sitter isn't free, whatever her weekly hours say."""

    __tablename__ = "days_off"

    sitter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sitters.profile_id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    created_at: Mapped[datetime] = created_at()


class GeocodeCache(Base):
    """Nominatim results, kept so each address is looked up once (CLAUDE.md 3: cache results)."""

    __tablename__ = "geocode_cache"
    __table_args__ = (
        CheckConstraint("lat BETWEEN -90 AND 90", name="lat_range"),
        CheckConstraint("lng BETWEEN -180 AND 180", name="lng_range"),
    )

    query: Mapped[str] = mapped_column(Text, primary_key=True)
    lat: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    lng: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    created_at: Mapped[datetime] = created_at()
