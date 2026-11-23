"""Suspending, removing and reinstating accounts (CLAUDE.md 6.6, 6.9, 6.11; phase 10 "User management").

Every change to an account's status is a row here, kept as written: who did it (an admin, or no one when
the rules did, as with a 5th strike or a parent's theft or abuse report), what kind of reason and the
reason itself. The person is emailed the reason (Reuben, 2026-11-22). Appeals (6.12) use `admin_id` to
keep the original decider off the appeal. Closing their own account (6.13) is a row too, with no admin.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import created_at, enum_column, uuid_pk


class AccountAction(StrEnum):
    suspended = "suspended"
    removed = "removed"
    reinstated = "reinstated"  # also reopening a closed account
    closed = "closed"  # by the person themselves (6.13): no admin, no kind


class AccountActionKind(StrEnum):
    """Why an account was suspended or removed. A removal for low ratings waits for her response, or the
    end of her 12 hours (6.11); the others don't wait (Reuben, 2026-11-22)."""

    low_ratings = "low_ratings"
    safety = "safety"  # safety or conduct, such as a theft or abuse report (6.9)
    strikes = "strikes"
    other = "other"


class AccountActionRow(Base):
    __tablename__ = "account_actions"
    __table_args__ = (
        CheckConstraint("(action IN ('suspended', 'removed')) = (kind IS NOT NULL)", name="kind_when_blocked"),
        CheckConstraint("action <> 'closed' OR admin_id IS NULL", name="closed_by_the_person"),
        Index("ix_account_actions_profile_id_created_at", "profile_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    action: Mapped[AccountAction] = mapped_column(enum_column(AccountAction, "account_action"))
    kind: Mapped[AccountActionKind | None] = mapped_column(enum_column(AccountActionKind, "account_action_kind"))
    reason: Mapped[str] = mapped_column(Text)  # shown to the person in the email
    admin_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = created_at()
