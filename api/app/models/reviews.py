"""Reviews and the low-rating flag (CLAUDE.md 6.11 and 8; phase 9).

After a booking where care happened (checked out, or closed by an admin after she checked in), the parent
and the sitter can each leave a 1-5 rating and a short review of the other, once, within 14 days of its
end (Reuben, 2026-11-22). Reviews are kept as written: the API's role can add rows only.

Parents see a sitter's average, count and written reviews on her profile; only admins see a sitter's
review of a parent (Reuben, 2026-11-22).

When the average of a sitter's last 10 reviews (once she has at least 5; Reuben, 2026-11-22) falls below
3.5, she's flagged for admin review. Before any removal for ratings she must be told the reason and given a
chance to respond, which is recorded: a flag is told, answered and closed in place, never deleted.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import enum_column, uuid_pk


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
        CheckConstraint("author_id <> subject_id", name="not_about_self"),
        # Once per author per booking.
        Index("uq_reviews_booking_id_author_id", "booking_id", "author_id", unique=True),
        Index("ix_reviews_subject_id_created_at", "subject_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id", ondelete="RESTRICT"))
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    rating: Mapped[int] = mapped_column(Integer)
    body: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class RatingFlagStatus(StrEnum):
    open = "open"  # flagged; an admin hasn't told her yet
    told = "told"  # an admin has told her the reason; waiting for her response
    responded = "responded"  # she has responded
    closed = "closed"  # an admin has decided, with a note


# Columns the API's database role may update: the flag's progress. Never what triggered it.
PROGRESS_COLUMNS = (
    "status",
    "told_by",
    "told_at",
    "reason",
    "response",
    "responded_at",
    "closed_by",
    "closed_at",
    "close_note",
)


class RatingFlag(Base):
    __tablename__ = "rating_flags"
    __table_args__ = (
        CheckConstraint("average >= 1 AND average < 3.5", name="average_low"),
        CheckConstraint("reviews_counted BETWEEN 5 AND 10", name="reviews_counted_range"),
        CheckConstraint(
            "(told_at IS NULL) = (told_by IS NULL) AND (told_at IS NULL) = (reason IS NULL)", name="told_has_reason"
        ),
        CheckConstraint("(responded_at IS NULL) = (response IS NULL)", name="response_has_time"),
        CheckConstraint("responded_at IS NULL OR told_at IS NOT NULL", name="responded_after_told"),
        CheckConstraint(
            "(closed_at IS NULL) = (closed_by IS NULL) AND (closed_at IS NULL) = (close_note IS NULL)",
            name="closed_has_note",
        ),
        CheckConstraint("(status = 'closed') = (closed_at IS NOT NULL)", name="closed_status"),
        # One flag in progress per sitter at a time.
        Index(
            "uq_rating_flags_sitter_id_not_closed",
            "sitter_id",
            unique=True,
            postgresql_where=text("status <> 'closed'"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    sitter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sitters.profile_id", ondelete="RESTRICT"))
    average: Mapped[Decimal] = mapped_column(Numeric(3, 2))  # of her last 10 reviews when flagged
    reviews_counted: Mapped[int] = mapped_column(Integer)
    status: Mapped[RatingFlagStatus] = mapped_column(
        enum_column(RatingFlagStatus, "rating_flag_status"), server_default=RatingFlagStatus.open.value
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    told_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    told_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)  # what the admin told her, shown to her
    response: Mapped[str | None] = mapped_column(Text)  # hers, in her words
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_note: Mapped[str | None] = mapped_column(Text)  # the admin's decision, internal
