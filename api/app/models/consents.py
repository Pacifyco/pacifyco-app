import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import created_at, enum_column, uuid_pk


class ConsentKind(StrEnum):
    """Family Terms 11.2 (CLAUDE.md section 7). The first four are required at sign-up; marketing is
    optional and withdrawable."""

    own_data = "own_data"
    child_data = "child_data"
    share_care_details = "share_care_details"
    emergency_authorisation = "emergency_authorisation"
    marketing = "marketing"


class Consent(Base):
    """One row per time a parent ticks (or, for marketing, un-ticks) a consent (CLAUDE.md 7).
    Append-only: withdrawing marketing adds a new row with accepted=false; existing rows are never
    changed or deleted by the API. No unique constraint: a required kind is only ever inserted once
    (the service checks first), but marketing can have several rows over time as it's toggled."""

    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = uuid_pk()
    # RESTRICT: a consent record outlives any attempt to delete the parent's account.
    parent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parents.profile_id", ondelete="RESTRICT"), index=True)
    kind: Mapped[ConsentKind] = mapped_column(enum_column(ConsentKind, "consent_kind"))
    version: Mapped[str] = mapped_column(Text)
    accepted: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = created_at()
