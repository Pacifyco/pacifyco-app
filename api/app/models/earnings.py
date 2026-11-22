"""What a sitter has earned (CLAUDE.md 6.2, 6.5, 6.8, 6.10; phase 9).

One row per amount she's owed for a booking: her pay for the hours worked, her overtime pay, or a fee
from a confirmed report (the show-up fee, or the flat ₹100 when only a man is home). Amounts are never
changed: the API's role can only move a row through held -> released -> paid and set when it's due.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import enum_column, uuid_pk
from app.models.sitters import PayoutMethod


class EarningKind(StrEnum):
    booking = "booking"  # level pay for hours worked (or the hours an admin or a report decides)
    overtime = "overtime"  # level pay for the rounded-up overtime hours (6.8)
    show_up_fee = "show_up_fee"  # ₹100 per booked hour (no one home), or a flat ₹100 (only a man home)


class EarningStatus(StrEnum):
    held = "held"  # the booking isn't finished, an overtime request is waiting, or an incident is open
    released = "released"  # due within 12 hours (6.10)
    paid = "paid"


# Columns the API's database role may update: the row's progress. Never the amount.
PROGRESS_COLUMNS = ("status", "released_at", "due_by", "payout_id")


class SitterEarning(Base):
    __tablename__ = "sitter_earnings"
    __table_args__ = (
        CheckConstraint("amount_paise > 0", name="amount_positive"),
        CheckConstraint("minutes IS NULL OR minutes > 0", name="minutes_positive"),
        CheckConstraint("(status = 'held') = (due_by IS NULL)", name="due_once_released"),
        CheckConstraint("(status = 'paid') = (payout_id IS NOT NULL)", name="paid_has_payout"),
        # One of each kind per booking.
        Index("uq_sitter_earnings_booking_id_kind", "booking_id", "kind", unique=True),
        Index("ix_sitter_earnings_sitter_id_status", "sitter_id", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    sitter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sitters.profile_id", ondelete="RESTRICT"))
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id", ondelete="RESTRICT"))
    kind: Mapped[EarningKind] = mapped_column(enum_column(EarningKind, "earning_kind"))
    amount_paise: Mapped[int] = mapped_column(Integer)
    minutes: Mapped[int | None] = mapped_column(Integer)  # the time it pays for, where it's time
    status: Mapped[EarningStatus] = mapped_column(
        enum_column(EarningStatus, "earning_status"), server_default=EarningStatus.held.value
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_by: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payout_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payouts.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class Payout(Base):
    """One transfer to a sitter for everything due to her (Reuben, 2026-11-22), marked paid by an admin with
    the UPI or bank transfer reference (6.10). Kept as written: the API's role can add rows only."""

    __tablename__ = "payouts"
    __table_args__ = (
        CheckConstraint("amount_paise > 0", name="amount_positive"),
        Index("uq_payouts_transfer_reference", "transfer_reference", unique=True),
        Index("ix_payouts_sitter_id_paid_at", "sitter_id", "paid_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    sitter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sitters.profile_id", ondelete="RESTRICT"))
    amount_paise: Mapped[int] = mapped_column(Integer)
    method: Mapped[PayoutMethod] = mapped_column(enum_column(PayoutMethod, "payout_method"))
    transfer_reference: Mapped[str] = mapped_column(Text)
    paid_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
