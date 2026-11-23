"""Emergencies and issues during a booking (CLAUDE.md 6.9 and 6.12; phase 8).

- Incident (the Emergency button): every admin is emailed at once, and it shows at the top of the admin
  panel until acknowledged; an admin then phones both people. A parent's theft or abuse report suspends the
  sitter immediately until an admin resolves it. An open incident holds the sitter's payout for that booking
  (payouts, phase 9).
- Complaint: raised from Help ("Raise a complaint") or the Issues button on a booking, or an appeal against a
  suspension or removal (type `suspension`, linked to the `account_actions` row). The complaints process
  (6.12, phase 10) is in `app/services/complaints.py`: reply and resolve targets, escalation to the
  Grievance Officer, appeals decided by an admin who didn't make the decision.
"""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Text
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
    # CLAUDE.md 8. `suspension` is an appeal; `data_request` comes with data requests (phase 10).
    booking = "booking"
    payment = "payment"
    family = "family"
    sitter = "sitter"
    review = "review"
    suspension = "suspension"
    data_request = "data_request"
    other = "other"


class ComplaintStatus(StrEnum):
    open = "open"  # waiting for Pacifyco's first reply
    replied = "replied"
    resolved = "resolved"  # an admin resolved it (or decided the appeal); the person can still escalate
    escalated = "escalated"  # with the Grievance Officer
    appealed = "appealed"  # not used: appeals are complaints of type `suspension`
    closed = "closed"  # the Grievance Officer's written decision: final


class DataRequestKind(StrEnum):
    """A data request (6.13), handled by an admin by hand (Reuben, 2026-11-23)."""

    access = "access"  # a copy of what Pacifyco holds about them
    correction = "correction"
    deletion = "deletion"  # what the law requires is kept


class AppealOutcome(StrEnum):
    upheld = "upheld"  # the decision is overturned (the account reinstated now, or by hand later)
    rejected = "rejected"  # the decision stands


class IssueTopic(StrEnum):
    running_late = "running_late"
    other = "other"


class Complaint(Base):
    __tablename__ = "complaints"
    __table_args__ = (
        CheckConstraint("description <> ''", name="description_not_empty"),
        CheckConstraint("(type = 'suspension') = (account_action_id IS NOT NULL)", name="appeal_has_decision"),
        CheckConstraint("appeal_outcome IS NULL OR type = 'suspension'", name="outcome_only_on_appeals"),
        CheckConstraint("(type = 'data_request') = (request_kind IS NOT NULL)", name="data_request_has_kind"),
        CheckConstraint("(escalated_at IS NULL) OR status IN ('escalated', 'closed')", name="escalated_status"),
        CheckConstraint("(officer_decided_at IS NULL) = (officer_decision IS NULL)", name="officer_decision_has_text"),
        Index("ix_complaints_status", "status"),
        Index("ix_complaints_raised_by", "raised_by"),
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
    # The complaints process (6.12, phase 10).
    happened_on: Mapped[date | None] = mapped_column(Date)  # India date, when the person gives one
    serious: Mapped[bool] = mapped_column(Boolean, server_default="false")  # a serious safety matter: 15 days
    reply_by: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # 24 hours
    # 48 hours; 15 days for a serious safety matter; an appeal's 7 working days
    resolve_by: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(Text)  # what the admin did, sent to the person
    account_action_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("account_actions.id", ondelete="RESTRICT"), unique=True
    )  # an appeal: the suspension or removal it's against, one appeal per decision
    appeal_outcome: Mapped[AppealOutcome | None] = mapped_column(enum_column(AppealOutcome, "appeal_outcome"))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="RESTRICT")
    )  # the person, when they disagreed; None when it was overdue
    escalation_note: Mapped[str | None] = mapped_column(Text)  # why the person disagrees
    officer_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    officer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    officer_decision: Mapped[str | None] = mapped_column(Text)  # written, with reasons; sent to the person
    officer_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A data request (6.13): what they're asking for.
    request_kind: Mapped[DataRequestKind | None] = mapped_column(enum_column(DataRequestKind, "data_request_kind"))


class ComplaintMessage(Base):
    """A written message on a complaint, from the person or from Pacifyco (an admin). Append-only."""

    __tablename__ = "complaint_messages"
    __table_args__ = (CheckConstraint("body <> ''", name="body_not_empty"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    complaint_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("complaints.id", ondelete="RESTRICT"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()


class PublicHoliday(Base):
    """A public holiday, added by admins: not a working day when counting an appeal's 7 working days."""

    __tablename__ = "public_holidays"
    __table_args__ = (CheckConstraint("name <> ''", name="name_not_empty"),)

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
