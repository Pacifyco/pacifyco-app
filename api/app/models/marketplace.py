"""The marketplace (CLAUDE.md 8, phase 5): sitters' free times, and cached geocoding results."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import created_at, uuid_pk


class AvailabilitySlot(Base):
    """A dated time a sitter is free (design.md: availability as dated time slots, not weekday toggles)."""

    __tablename__ = "availability_slots"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ends_after_start"),
        Index("ix_availability_slots_sitter_id_starts_at", "sitter_id", "starts_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    sitter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sitters.profile_id", ondelete="CASCADE"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
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
