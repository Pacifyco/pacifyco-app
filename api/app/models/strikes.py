"""Strikes against sitters (CLAUDE.md 6.5, 6.6 and 8).

A strike is given for a late cancellation (less than 8 hours before the start) or a confirmed no-show.
Each expires 6 months after it was given; only strikes from the last 6 months count. Strikes are kept:
an admin can remove one with a reason (for example, a doctor's note for an illness), which records who
and when, but a strike is never deleted. The ladder and blocking come with phase 7 "Strikes".
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import enum_column, uuid_pk


class StrikeReason(StrEnum):
    late_cancellation = "late_cancellation"
    no_show = "no_show"
    admin = "admin"  # added by an admin, with a note


# Columns the API's database role may update: recording a removal. Nothing else changes.
REMOVAL_COLUMNS = ("removed_by", "removed_at", "removal_reason", "doctor_note_document_id")


class Strike(Base):
    __tablename__ = "strikes"
    __table_args__ = (
        CheckConstraint("expires_at > given_at", name="expires_after_given"),
        CheckConstraint(
            "(removed_at IS NULL) = (removed_by IS NULL) AND (removed_at IS NULL OR removal_reason IS NOT NULL)",
            name="removal_has_who_and_reason",
        ),
        Index("ix_strikes_sitter_id_given_at", "sitter_id", "given_at"),
        # One strike per booking.
        Index("uq_strikes_booking_id", "booking_id", unique=True, postgresql_where=text("booking_id IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    sitter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sitters.profile_id", ondelete="RESTRICT"))
    booking_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bookings.id", ondelete="RESTRICT"))
    reason: Mapped[StrikeReason] = mapped_column(enum_column(StrikeReason, "strike_reason"))
    note: Mapped[str | None] = mapped_column(Text)
    given_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    removed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removal_reason: Mapped[str | None] = mapped_column(Text)
    doctor_note_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="RESTRICT"))
