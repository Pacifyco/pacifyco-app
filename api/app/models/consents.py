import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import created_at, uuid_pk


class Consent(Base):
    """A parent's acceptance of one version of the parental consent form (CLAUDE.md 7). Append-only:
    accepting a new version adds a row; rows are never changed or deleted by the API."""

    __tablename__ = "consents"
    # Accepting the same version twice keeps the first record.
    __table_args__ = (UniqueConstraint("parent_id", "form_version"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    # RESTRICT: a consent record outlives any attempt to delete the parent's account.
    parent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parents.profile_id", ondelete="RESTRICT"), index=True)
    form_version: Mapped[str] = mapped_column(Text)
    accepted_at: Mapped[datetime] = created_at()
