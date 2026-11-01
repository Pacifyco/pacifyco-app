import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import created_at, enum_column, uuid_pk


class LegalKind(StrEnum):
    parent_terms = "parent_terms"
    sitter_terms = "sitter_terms"
    privacy_policy = "privacy_policy"


class AcceptanceMethod(StrEnum):
    clickwrap = "clickwrap"  # Aadhaar e-sign for sitters is planned for later (CLAUDE.md 10)


class LegalDocument(Base):
    """One version of a legal document (CLAUDE.md 7). Rows are added by migrations when a version is
    published; the current version of a kind is the latest whose effective_at has passed."""

    __tablename__ = "legal_documents"
    __table_args__ = (UniqueConstraint("kind", "version"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[LegalKind] = mapped_column(enum_column(LegalKind, "legal_document_kind"))
    version: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = created_at()
    # Changes to the sitter terms that affect pay or rights take effect at least 14 days after publishing.
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_path: Mapped[str] = mapped_column(Text)  # the file in web/src/content


class LegalAcceptance(Base):
    """Someone accepting one version of a document. Append-only for the API; never deleted."""

    __tablename__ = "legal_acceptances"
    __table_args__ = (UniqueConstraint("profile_id", "document_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_documents.id", ondelete="RESTRICT"))
    method: Mapped[AcceptanceMethod] = mapped_column(
        enum_column(AcceptanceMethod, "legal_acceptance_method"), server_default=AcceptanceMethod.clickwrap.value
    )
    accepted_at: Mapped[datetime] = created_at()
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
