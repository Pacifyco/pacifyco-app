import uuid
from datetime import date

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import VerificationStatus, enum_column, uuid_pk


class Parent(Base):
    __tablename__ = "parents"

    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    second_parent_name: Mapped[str | None] = mapped_column(Text)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        enum_column(VerificationStatus, "parent_verification_status"),
        server_default=VerificationStatus.pending.value,
    )


class Child(Base):
    __tablename__ = "children"

    id: Mapped[uuid.UUID] = uuid_pk()
    parent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parents.profile_id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(Text)
    # Required: bookings are only allowed for children 18 months and older on the booking date (6.4).
    date_of_birth: Mapped[date]
    allergies: Mapped[str | None] = mapped_column(Text)
    medical_notes: Mapped[str | None] = mapped_column(Text)
    routines: Mapped[str | None] = mapped_column(Text)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        enum_column(VerificationStatus, "child_verification_status"),
        server_default=VerificationStatus.pending.value,
    )


class EmergencyContact(Base):
    __tablename__ = "emergency_contacts"

    id: Mapped[uuid.UUID] = uuid_pk()
    child_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("children.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(Text)
    relationship: Mapped[str] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(String(20))
