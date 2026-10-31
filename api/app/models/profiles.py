import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CHAR, CheckConstraint, Numeric, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import created_at, enum_column


class Role(StrEnum):
    parent = "parent"
    sitter = "sitter"
    admin = "admin"


class ProfileStatus(StrEnum):
    pending = "pending"
    active = "active"
    suspended = "suspended"
    removed = "removed"


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint("pin_code ~ '^[0-9]{6}$'", name="pin_code_format"),
        CheckConstraint("lat BETWEEN -90 AND 90", name="lat_range"),
        CheckConstraint("lng BETWEEN -180 AND 180", name="lng_range"),
    )

    # Same id as the Supabase auth user (not a foreign key: auth lives in Supabase's own schema).
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    role: Mapped[Role] = mapped_column(enum_column(Role, "profile_role"))
    full_name: Mapped[str] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str] = mapped_column(Text, unique=True)
    status: Mapped[ProfileStatus] = mapped_column(
        enum_column(ProfileStatus, "profile_status"), server_default=ProfileStatus.pending.value
    )
    pin_code: Mapped[str | None] = mapped_column(CHAR(6))
    address: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    created_at: Mapped[datetime] = created_at()


class ServiceAreaPincode(Base):
    """Pin codes where sign-up and bookings are allowed (seeded by the first migration)."""

    __tablename__ = "service_area_pincodes"
    __table_args__ = (CheckConstraint("pin_code ~ '^[0-9]{6}$'", name="pin_code_format"),)

    pin_code: Mapped[str] = mapped_column(CHAR(6), primary_key=True)
    active: Mapped[bool] = mapped_column(server_default=true())
