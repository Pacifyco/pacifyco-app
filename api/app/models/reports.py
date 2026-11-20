"""Reports during a booking (CLAUDE.md 6.5; phase 7): the parent wasn't home, or the sitter didn't come.

- Parent not home: the sitter reports it. She may leave, and is paid the show-up fee (₹100 per booked hour),
  only if no parent responds within 20 minutes of the report. The parent responds in the app ("I have
  arrived") or an admin marks that they answered the phone (Reuben, 2026-11-19). An admin confirms it; the
  parent pays for the whole booking.
- Sitter no-show: the parent reports it, from 30 minutes after the start (Reuben, 2026-11-19). An admin
  confirms it; the parent is refunded and the sitter gets a strike and earns nothing.

Each decision is audit logged; a dismissed report changes nothing.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import enum_column, uuid_pk


class ReportKind(StrEnum):
    parent_absent = "parent_absent"
    sitter_no_show = "sitter_no_show"
    # The only adult at home is a man: she may decline on the spot (6.5; decided 2026-11-12).
    only_man_home = "only_man_home"


class ReportStatus(StrEnum):
    open = "open"
    confirmed = "confirmed"
    dismissed = "dismissed"


class BookingReport(Base):
    __tablename__ = "booking_reports"
    __table_args__ = (
        CheckConstraint("(status = 'open') = (decided_at IS NULL)", name="decided_unless_open"),
        CheckConstraint("(responded_at IS NULL) = (responded_by IS NULL)", name="response_has_who"),
        Index("ix_booking_reports_status", "status"),
        # One report of each kind per booking.
        Index("uq_booking_reports_booking_id_kind", "booking_id", "kind", unique=True),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id", ondelete="RESTRICT"))
    kind: Mapped[ReportKind] = mapped_column(enum_column(ReportKind, "report_kind"))
    reported_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    # Parent not home: when a parent responded (the parent in the app, or an admin after a call).
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    status: Mapped[ReportStatus] = mapped_column(
        enum_column(ReportStatus, "report_status"), server_default=ReportStatus.open.value
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
