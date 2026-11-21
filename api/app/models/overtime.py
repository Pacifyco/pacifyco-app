"""Overtime requests (CLAUDE.md 6.8; phase 8). During the booking the parent asks for extra whole hours;
the sitter accepts or declines. Nothing is charged here -- overtime is always worked out at check-out,
whether or not a request was ever made, and a parent simply running late still owes it."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, SmallInteger, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import enum_column, uuid_pk


class OvertimeRequestStatus(StrEnum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"


class OvertimeRequest(Base):
    __tablename__ = "overtime_requests"
    __table_args__ = (
        CheckConstraint("requested_hours >= 1", name="requested_hours_positive"),
        CheckConstraint("(status = 'pending') = (decided_at IS NULL)", name="decided_unless_pending"),
        # Only one open request per booking at a time (also checked in the service).
        Index(
            "uq_overtime_requests_booking_id_pending",
            "booking_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id", ondelete="RESTRICT"))
    requested_hours: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[OvertimeRequestStatus] = mapped_column(
        enum_column(OvertimeRequestStatus, "overtime_request_status"),
        server_default=OvertimeRequestStatus.pending.value,
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OvertimeCharge(Base):
    """Worked out at check-out (6.8): whether or not a request was ever made, extra time past the
    booked end is rounded up to the full hour and charged. Its payment is a separate `payments` row
    (kind=overtime); this row is the record of how the amount was worked out."""

    __tablename__ = "overtime_charges"
    __table_args__ = (
        CheckConstraint("minutes_over >= 0", name="minutes_over_not_negative"),
        CheckConstraint("hours_charged >= 1", name="hours_charged_positive"),
        CheckConstraint("amount_paise >= 0", name="amount_paise_not_negative"),
        CheckConstraint("sitter_pay_paise >= 0", name="sitter_pay_paise_not_negative"),
        # Overtime is worked out once, at check-out.
        Index("uq_overtime_charges_booking_id", "booking_id", unique=True),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id", ondelete="RESTRICT"))
    minutes_over: Mapped[int] = mapped_column(Integer)
    hours_charged: Mapped[int] = mapped_column(SmallInteger)
    amount_paise: Mapped[int] = mapped_column(Integer)
    sitter_pay_paise: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
