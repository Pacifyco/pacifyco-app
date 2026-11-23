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
    # An unpaid overtime or cancellation charge an admin let go, with a reason (Reuben, 2026-11-23). It's no
    # longer owed, so it stops blocking new bookings; the row is kept.
    waived = "waived"


# Columns that can change after a row is added (see the migrations' grants): an admin's decision, and a
# charge's UPI reference (sent by the parent, cleared if rejected). Nothing else, never an amount.
DECISION_COLUMNS = (
    "status",
    "confirmed_by",
    "confirmed_at",
    "rejection_reason",
    "transfer_reference",
    "upi_reference",
    "waive_reason",
)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount_paise <> 0", name="amount_not_zero"),
        CheckConstraint("upi_reference IS NULL OR upi_reference ~ '^[0-9]{12}$'", name="upi_reference_12_digits"),
        CheckConstraint("status <> 'rejected' OR rejection_reason IS NOT NULL", name="rejection_has_reason"),
        CheckConstraint("(status = 'waived') = (waive_reason IS NOT NULL)", name="waived_has_reason"),
        CheckConstraint(
            "status <> 'waived' OR kind IN ('overtime', 'cancellation_charge')", name="only_charges_waived"
        ),
        # A refund is paid back by UPI or bank transfer; marking it paid records that transfer's reference.
        CheckConstraint(
            "kind <> 'refund' OR status <> 'confirmed' OR transfer_reference IS NOT NULL",
            name="refund_paid_has_reference",
        ),
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
    # Refunds: the UPI or bank transfer reference Pacifyco paid the money back with.
    transfer_reference: Mapped[str | None] = mapped_column(Text)
    waive_reason: Mapped[str | None] = mapped_column(Text)  # why an admin waived a charge; shown to the parent
    created_at: Mapped[datetime] = created_at()
