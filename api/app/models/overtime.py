"""Overtime requests (CLAUDE.md 6.8; phase 8). During the booking the parent asks for extra whole hours;
the sitter accepts or declines. Nothing is charged here -- overtime is always worked out at check-out,
whether or not a request was ever made, and a parent simply running late still owes it."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, SmallInteger, text
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
