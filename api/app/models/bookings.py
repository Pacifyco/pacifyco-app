"""Bookings (CLAUDE.md 6.4 and 8). A booking is made with one sitter for whole hours, at her plan's price,
starts as a request the sitter accepts or declines (6.4), then waits as `pending_payment` until an admin
confirms the parent's UPI payment (6.1).

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
    # A request: the sitter accepts or declines before the parent pays (Reuben, 2026-11-19). She sees it
    # once every child on it is verified; unanswered in time, it lapses (6.4).
    requested = "requested"
    request_declined = "request_declined"
    request_lapsed = "request_lapsed"
    # Accepted by the sitter, holding her time while the parent pays (6.1, 6.4).
    pending_payment = "pending_payment"
    # Paid, but a child on it isn't verified yet: it holds her time and becomes `confirmed` when the last
    # child is approved (Reuben, 2026-11-18). The sitter doesn't see it until then (6.4).
    awaiting_verification = "awaiting_verification"
    confirmed = "confirmed"
    in_progress = "in_progress"
    completed = "completed"
    cancelled_parent = "cancelled_parent"
    cancelled_parent_late = "cancelled_parent_late"
    cancelled_sitter = "cancelled_sitter"
    cancelled_sitter_late = "cancelled_sitter_late"
    parent_absent = "parent_absent"
    sitter_no_show = "sitter_no_show"
    # Cancelled by Pacifyco while waiting for payment (6.1, 6.4): not paid by the deadline, 3 hours before
    # the start; or another booking for an overlapping time with her was confirmed first.
    cancelled_unpaid = "cancelled_unpaid"
    cancelled_slot_taken = "cancelled_slot_taken"
    # Paid, but a child on it still wasn't verified when it started: refunded (Reuben, 2026-11-18).
    cancelled_unverified = "cancelled_unverified"
    # The sitter declined on arrival: the only adult at home was a man (6.5). Charged in full; no strike;
    # Pacifyco pays her a flat ₹100.
    declined_man_at_home = "declined_man_at_home"
    # A child on the booking was under 18 months, which should never happen (6.5). Parent charged for 1
    # hour, refunded the rest; sitter paid her level pay for that hour; no strike.
    child_under_age = "child_under_age"
    # She left because she felt unsafe, once the child was with a parent (6.5). Charged in full (kept
    # from the Family Terms); she's paid for the time she worked (phase 9); no strike.
    sitter_left_unsafe = "sitter_left_unsafe"


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
        enum_column(BookingStatus, "booking_status"), server_default=BookingStatus.requested.value
    )
    # When the sitter could first see the request: every child on it verified (6.4). Her 5 hours to answer
    # run from then.
    request_visible_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
