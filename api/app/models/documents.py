import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import created_at, enum_column, uuid_pk


class DocumentType(StrEnum):
    """CLAUDE.md section 8. Which role/form uploads which type is enforced by that form, not here."""

    birth_certificate = "birth_certificate"
    government_id = "government_id"
    college_or_work_id = "college_or_work_id"
    police_certificate = "police_certificate"
    first_aid_certificate = "first_aid_certificate"
    doctor_note = "doctor_note"
    photo = "photo"


class DocumentStatus(StrEnum):
    pending_upload = "pending_upload"  # a signed upload URL was issued; nothing confirmed yet
    uploaded = "uploaded"  # confirmed: real content is a PDF/JPG/PNG within the size limit
    invalid = "invalid"  # confirmed, but the content failed the type or size check; file deleted


class Document(Base):
    """A private file in Supabase Storage (CLAUDE.md section 5: uploads go through signed upload
    URLs issued by the API; viewed only by admins through short-lived signed URLs). `storage_path`
    is the object's path within the private `documents` bucket."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"), index=True)
    child_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("children.id", ondelete="RESTRICT"), index=True)
    type: Mapped[DocumentType] = mapped_column(enum_column(DocumentType, "document_type"))
    storage_path: Mapped[str] = mapped_column(Text, unique=True)
    status: Mapped[DocumentStatus] = mapped_column(
        enum_column(DocumentStatus, "document_status"), server_default=DocumentStatus.pending_upload.value
    )
    created_at: Mapped[datetime] = created_at()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentAccessLog(Base):
    """Every admin view of a document (CLAUDE.md section 5). Append-only."""

    __tablename__ = "document_access_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="RESTRICT"), index=True)
    admin_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"), index=True)
    accessed_at: Mapped[datetime] = created_at()
