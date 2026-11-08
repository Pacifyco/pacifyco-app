import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import ARRAY, CheckConstraint, DateTime, ForeignKey, LargeBinary, Numeric, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import VerificationStatus, enum_column, uuid_pk


class PayoutMethod(StrEnum):
    bank = "bank"
    upi = "upi"


class SitterLevel(StrEnum):
    """CLAUDE.md 6.2: set by an admin; a sitter works only her own level's plan."""

    pause = "pause"
    unwind = "unwind"
    recharge = "recharge"


class OnboardingStepName(StrEnum):
    """The onboarding steps an admin reviews directly (CLAUDE.md 7 steps 1-3). References (step 4)
    and the psychology test (step 5) keep their own outcomes, on `references` and `psych_attempts`."""

    profile = "profile"
    identity_documents = "identity_documents"
    police_certificate = "police_certificate"


class OnboardingStatus(StrEnum):
    in_progress = "in_progress"
    approved = "approved"
    rejected = "rejected"


class Sitter(Base):
    __tablename__ = "sitters"
    __table_args__ = (
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
    onboarding_status: Mapped[OnboardingStatus] = mapped_column(
        enum_column(OnboardingStatus, "sitter_onboarding_status"),
        server_default=OnboardingStatus.in_progress.value,
    )
    # Null until an admin sets it; she can't go live without one (CLAUDE.md 6.2 and 7 step 6).
    level: Mapped[SitterLevel | None] = mapped_column(enum_column(SitterLevel, "sitter_level"))
    # Her tick in the application: at Recharge level, parents may see one of her references (CLAUDE.md 6.2).
    reference_shared_consent: Mapped[bool] = mapped_column(server_default=false())
    avg_rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    review_count: Mapped[int] = mapped_column(server_default="0")


class Reference(Base):
    """Two references per sitter (name, phone, relationship), CLAUDE.md section 7 step 4. An admin
    records the outcome; `pending` until then (phase 3's admin verification queue)."""

    __tablename__ = "references"

    id: Mapped[uuid.UUID] = uuid_pk()
    sitter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sitters.profile_id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(String(20))
    relationship: Mapped[str] = mapped_column(Text)
    outcome: Mapped[VerificationStatus] = mapped_column(
        enum_column(VerificationStatus, "reference_outcome"), server_default=VerificationStatus.pending.value
    )
    notes: Mapped[str | None] = mapped_column(Text)


class OnboardingStep(Base):
    """An admin's review of one onboarding step (CLAUDE.md 7). No row means not reviewed yet."""

    __tablename__ = "onboarding_steps"

    sitter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sitters.profile_id", ondelete="CASCADE"), primary_key=True)
    step: Mapped[OnboardingStepName] = mapped_column(
        enum_column(OnboardingStepName, "onboarding_step"), primary_key=True
    )
    status: Mapped[VerificationStatus] = mapped_column(enum_column(VerificationStatus, "onboarding_step_status"))
    notes: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
