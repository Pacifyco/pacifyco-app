"""Emergencies and issues during a booking (CLAUDE.md 6.9 and 6.12; phase 8).

- Incident (the Emergency button): every admin is emailed at once, and it shows at the top of the admin
  panel until acknowledged; an admin then phones both people. A parent's theft or abuse report suspends the
  sitter immediately until an admin resolves it. An open incident holds the sitter's payout for that booking
  (payouts, phase 9).
- Complaint (the Issues button): a non-emergency issue, such as running late, linked to the booking. The
  full complaints process (reply and resolve targets, escalation, appeals, 6.12) comes later; for now admins
  mark it replied and resolved.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import created_at, enum_column, uuid_pk


class IncidentKind(StrEnum):
    emergency = "emergency"  # safety or medical, either side
    theft = "theft"  # parent about the sitter: suspends her
    abuse = "abuse"  # parent about the sitter: suspends her
    sitter_unsafe = "sitter_unsafe"  # the sitter is being abused or feels unsafe


class IncidentStatus(StrEnum):
    open = "open"
    acknowledged = "acknowledged"
    resolved = "resolved"


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint("(acknowledged_at IS NULL) = (acknowledged_by IS NULL)", name="acknowledged_has_who"),
        CheckConstraint("(resolved_at IS NULL) = (resolved_by IS NULL)", name="resolved_has_who"),
        Index("ix_incidents_status", "status"),
        Index("ix_incidents_booking_id", "booking_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id", ondelete="RESTRICT"))
    raised_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    kind: Mapped[IncidentKind] = mapped_column(enum_column(IncidentKind, "incident_kind"))
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[IncidentStatus] = mapped_column(
        enum_column(IncidentStatus, "incident_status"), server_default=IncidentStatus.open.value
    )
    # A theft or abuse report suspended the sitter (so resolving it decides whether she comes back).
    suspended_sitter: Mapped[bool] = mapped_column(Boolean, server_default="false")
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()


class ComplaintType(StrEnum):
    # CLAUDE.md 8; only `booking` is raised so far (the Issues button).
    booking = "booking"
    payment = "payment"
    family = "family"
    sitter = "sitter"
    review = "review"
    suspension = "suspension"
    data_request = "data_request"
    other = "other"


class ComplaintStatus(StrEnum):
    open = "open"
    replied = "replied"
    resolved = "resolved"
    escalated = "escalated"
    appealed = "appealed"
    closed = "closed"


class IssueTopic(StrEnum):
    running_late = "running_late"
    other = "other"


class Complaint(Base):
    __tablename__ = "complaints"
    __table_args__ = (
        CheckConstraint("description <> ''", name="description_not_empty"),
        Index("ix_complaints_status", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    raised_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    booking_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bookings.id", ondelete="RESTRICT"))
    type: Mapped[ComplaintType] = mapped_column(enum_column(ComplaintType, "complaint_type"))
    topic: Mapped[IssueTopic | None] = mapped_column(enum_column(IssueTopic, "issue_topic"))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[ComplaintStatus] = mapped_column(
        enum_column(ComplaintStatus, "complaint_status"), server_default=ComplaintStatus.open.value
    )
    late: Mapped[bool] = mapped_column(Boolean, server_default="false")  # raised over 24 hours after (6.12)
    first_reply_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = created_at()
