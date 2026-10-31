import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import ARRAY, CheckConstraint, ForeignKey, LargeBinary, Numeric, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import enum_column

# Sitter rate limits in paise: ₹80–₹120 per hour, per child (CLAUDE.md 6.2).
MIN_RATE_PAISE = 8_000
MAX_RATE_PAISE = 12_000


class PayoutMethod(StrEnum):
    bank = "bank"
    upi = "upi"


class OnboardingStatus(StrEnum):
    in_progress = "in_progress"
    approved = "approved"
    rejected = "rejected"


class Sitter(Base):
    __tablename__ = "sitters"
    __table_args__ = (
        CheckConstraint(
            f"hourly_rate_paise BETWEEN {MIN_RATE_PAISE} AND {MAX_RATE_PAISE}", name="hourly_rate_range"
        ),
        CheckConstraint("years_experience >= 0", name="years_experience_not_negative"),
        CheckConstraint("avg_rating BETWEEN 1 AND 5", name="avg_rating_range"),
        CheckConstraint("review_count >= 0", name="review_count_not_negative"),
    )

    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    date_of_birth: Mapped[date | None]
    # Encrypted by the API before storage (phase 3); admin-only, never shown to parents (CLAUDE.md 7).
    health_disclosure_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    payout_method: Mapped[PayoutMethod | None] = mapped_column(enum_column(PayoutMethod, "sitter_payout_method"))
    bank_details_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    upi_id: Mapped[str | None] = mapped_column(Text)
    bio: Mapped[str | None] = mapped_column(Text)
    years_experience: Mapped[int | None]
    age_groups: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    languages: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    first_aid: Mapped[bool] = mapped_column(server_default=false())
    # Parents never see this (6.2).
    hourly_rate_paise: Mapped[int | None]
    onboarding_status: Mapped[OnboardingStatus] = mapped_column(
        enum_column(OnboardingStatus, "sitter_onboarding_status"),
        server_default=OnboardingStatus.in_progress.value,
    )
    avg_rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    review_count: Mapped[int] = mapped_column(server_default="0")
