"""Money owed and paid (CLAUDE.md 5, 6.1 and 8). Append-only: each booking payment, overtime charge,
refund and cancellation charge is its own row and an amount is never changed. Only an admin's decision
on a payment (status, who and when, and a rejection reason) is written later; the API's database role
can update just those columns and can't delete rows.

Beta (manual UPI): the parent pays Pacifyco by UPI and enters the 12-digit UPI reference, which adds a
`pending` row; an admin confirms or rejects it. A rejected payment stays, and the parent can send a new
reference as a new row."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import created_at, enum_column, uuid_pk


class PaymentKind(StrEnum):
    booking = "booking"
    overtime = "overtime"
    refund = "refund"
    cancellation_charge = "cancellation_charge"


class PaymentStatus(StrEnum):
    pending = "pending"
    confirmed = "confirmed"
    rejected = "rejected"


# Columns an admin's decision writes; nothing else in a row can change (see the migration's grants).
DECISION_COLUMNS = ("status", "confirmed_by", "confirmed_at", "rejection_reason")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount_paise <> 0", name="amount_not_zero"),
        CheckConstraint("upi_reference IS NULL OR upi_reference ~ '^[0-9]{12}$'", name="upi_reference_12_digits"),
        CheckConstraint("status <> 'rejected' OR rejection_reason IS NOT NULL", name="rejection_has_reason"),
        Index("ix_payments_booking_id", "booking_id"),
        Index("ix_payments_parent_id", "parent_id"),
        # One UPI transaction pays for one thing: a reference can't be sent twice unless it was rejected.
        Index(
            "uq_payments_upi_reference",
            "upi_reference",
            unique=True,
            postgresql_where=text("upi_reference IS NOT NULL AND status <> 'rejected'"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id", ondelete="RESTRICT"))
    parent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parents.profile_id", ondelete="RESTRICT"))
    kind: Mapped[PaymentKind] = mapped_column(enum_column(PaymentKind, "payment_kind"))
    # + owed or paid by the parent, − refunded to them.
    amount_paise: Mapped[int] = mapped_column(Integer)
    status: Mapped[PaymentStatus] = mapped_column(
        enum_column(PaymentStatus, "payment_status"), server_default=PaymentStatus.pending.value
    )
    upi_reference: Mapped[str | None] = mapped_column(Text)
    due_by: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()
