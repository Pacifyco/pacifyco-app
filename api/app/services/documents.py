"""Verification documents (CLAUDE.md sections 5 and 7). The browser never talks to Storage directly:
it gets a signed upload URL from the API, uploads to it, then asks the API to confirm the upload.
Confirming is where the real check happens -- the bucket's own limits only look at the declared
content type, so the API downloads the file once and checks the actual bytes before trusting it.
Viewing a document is admin-only, through another short-lived signed URL, logged every time."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Child, Document, DocumentAccessLog, DocumentStatus, DocumentType, VerificationStatus
from app.services import consent
from app.services.storage import StorageClient

MAX_FILE_BYTES = 5 * 1024 * 1024

# Checked from the bytes themselves, not the filename or the declared content type (CLAUDE.md 7).
_SNIFFERS: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)


def sniff_content_type(data: bytes) -> str | None:
    """The file's real type, or None if it isn't a PDF, JPG or PNG."""
    return next((mime for magic, mime in _SNIFFERS if data.startswith(magic)), None)


@dataclass(frozen=True)
class UploadTicket:
    document_id: uuid.UUID
    upload_url: str


def request_upload(
    db: Session,
    storage: StorageClient,
    owner_profile_id: uuid.UUID,
    doc_type: DocumentType,
    child_id: uuid.UUID | None,
) -> UploadTicket:
    if child_id is not None:
        child = db.get(Child, child_id)
        if child is None or child.parent_id != owner_profile_id:
            raise AppError(403, "forbidden", "That child doesn't belong to you")
        consent.require_current_consent(db, owner_profile_id)  # CLAUDE.md 9 "Consent"

    document_id = uuid.uuid4()
    path = f"{owner_profile_id}/{document_id}"
    document = Document(
        id=document_id, owner_profile_id=owner_profile_id, child_id=child_id, type=doc_type, storage_path=path
    )
    db.add(document)
    upload_url = storage.create_signed_upload_url(path)  # if this fails, nothing is committed
    db.commit()
    return UploadTicket(document_id=document_id, upload_url=upload_url)


def _owned_document(db: Session, document_id: uuid.UUID, owner_profile_id: uuid.UUID) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise AppError(404, "not_found", "That document doesn't exist")
    if document.owner_profile_id != owner_profile_id:
        raise AppError(403, "forbidden", "This isn't your document")
    return document


def confirm_upload(
    db: Session, storage: StorageClient, owner_profile_id: uuid.UUID, document_id: uuid.UUID
) -> Document:
    document = _owned_document(db, document_id, owner_profile_id)
    if document.status != DocumentStatus.pending_upload:
        raise AppError(409, "already_confirmed", "This upload has already been checked")

    try:
        data = storage.download(document.storage_path)
    except AppError as exc:
        if exc.code == "storage_object_not_found":
            raise AppError(400, "upload_not_found", "Please upload the file before confirming it") from exc
        raise

    if sniff_content_type(data) is None or len(data) > MAX_FILE_BYTES:
        storage.delete(document.storage_path)
        document.status = DocumentStatus.invalid
        db.commit()
        message = "That file is larger than 5 MB" if len(data) > MAX_FILE_BYTES else "That file isn't a PDF, JPG or PNG"
        raise AppError(422, "invalid_file", message)

    document.status = DocumentStatus.uploaded
    if document.type == DocumentType.birth_certificate and document.child_id is not None:
        child = db.get(Child, document.child_id)
        if child is not None and child.verification_status == VerificationStatus.rejected:
            child.verification_status = VerificationStatus.pending  # a new certificate goes back for review
    db.commit()
    return document


def list_mine(
    db: Session, owner_profile_id: uuid.UUID, doc_type: DocumentType | None = None, child_id: uuid.UUID | None = None
) -> list[Document]:
    """So the web can show "uploaded" / "being checked" / "please try again" for its own uploads.
    Deleted documents (e.g. a birth certificate removed after verification) don't show at all."""
    query = select(Document).where(Document.owner_profile_id == owner_profile_id, Document.deleted_at.is_(None))
    if doc_type is not None:
        query = query.where(Document.type == doc_type)
    if child_id is not None:
        query = query.where(Document.child_id == child_id)
    return list(db.scalars(query.order_by(Document.created_at)))


def get_view_url(db: Session, storage: StorageClient, admin_id: uuid.UUID, document_id: uuid.UUID) -> str:
    document = db.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise AppError(404, "not_found", "That document doesn't exist")
    url = storage.create_signed_view_url(document.storage_path)
    db.add(DocumentAccessLog(document_id=document.id, admin_id=admin_id))
    db.commit()
    return url
