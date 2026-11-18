"""Bookings (CLAUDE.md 6.4 and 8). A booking is made with one sitter for whole hours, at her plan's price,
and waits as `pending_payment` until an admin confirms the parent's UPI payment (6.1).

Columns for check-in codes, locations and admin closing come with the phases that need them (7 and 8).
Parent and sitter links are RESTRICT: a booking is a money record and outlives any attempt to delete an
account."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import created_at, enum_column, uuid_pk
from app.models.sitters import SitterLevel


class BookingStatus(StrEnum):
    pending_payment = "pending_payment"
    confirmed = "confirmed"
    in_progress = "in_progress"
    completed = "completed"
    cancelled_parent = "cancelled_parent"
    cancelled_parent_late = "cancelled_parent_late"
    cancelled_sitter = "cancelled_sitter"
    cancelled_sitter_late = "cancelled_sitter_late"
    parent_absent = "parent_absent"
    sitter_no_show = "sitter_no_show"


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ends_after_start"),
        CheckConstraint("units >= 1", name="units_positive"),
        CheckConstraint("children_count >= 1", name="children_count_positive"),
        CheckConstraint("price_paise > 0", name="price_positive"),
        Index("ix_bookings_sitter_id_starts_at", "sitter_id", "starts_at"),
        Index("ix_bookings_parent_id", "parent_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    parent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parents.profile_id", ondelete="RESTRICT"))
    sitter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sitters.profile_id", ondelete="RESTRICT"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # The plan is the sitter's level when the booking was made (6.2); kept here so a later level change
    # doesn't change the price.
    plan: Mapped[SitterLevel] = mapped_column(enum_column(SitterLevel, "booking_plan"))
    units: Mapped[int] = mapped_column(SmallInteger)  # whole hours booked
    children_count: Mapped[int] = mapped_column(SmallInteger)
    price_paise: Mapped[int] = mapped_column(Integer)
    bath_time: Mapped[bool] = mapped_column(Boolean, server_default="false")
    status: Mapped[BookingStatus] = mapped_column(
        enum_column(BookingStatus, "booking_status"), server_default=BookingStatus.pending_payment.value
    )
    created_at: Mapped[datetime] = created_at()


class BookingChild(Base):
    """Who the sitter is caring for. Only the parent's own children (6.1)."""

    __tablename__ = "booking_children"

    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), primary_key=True)
    child_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("children.id", ondelete="RESTRICT"), primary_key=True)


class BookingHomeInfo(Base):
    """The parent's camera declaration (6.4): whether cameras are on and where. The sitter sees it before
    the booking starts."""

    __tablename__ = "booking_home_info"
    __table_args__ = (CheckConstraint("NOT cameras_on OR camera_locations IS NOT NULL", name="cameras_have_locations"),)

    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), primary_key=True)
    cameras_on: Mapped[bool] = mapped_column(Boolean)
    camera_locations: Mapped[str | None] = mapped_column(Text)
