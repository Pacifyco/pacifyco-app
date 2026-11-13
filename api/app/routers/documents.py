"""Uploading verification documents (CLAUDE.md sections 5 and 7). Both parents and sitters use this,
so it isn't under one role's area; each endpoint checks for itself (listed in PUBLIC in
tests/test_roles.py, which fails otherwise)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import current_profile
from app.deps import DbSession
from app.models import DocumentStatus, DocumentType, Profile
from app.services import documents
from app.services.storage import StorageClient, get_storage

router = APIRouter(prefix="/documents", tags=["documents"])
CurrentProfile = Annotated[Profile, Depends(current_profile)]
Storage = Annotated[StorageClient, Depends(get_storage)]


class RequestUpload(BaseModel):
    type: DocumentType
    child_id: uuid.UUID | None = None  # required for birth_certificate; must be the caller's own child


class UploadTicket(BaseModel):
    document_id: uuid.UUID
    upload_url: str  # PUT the file here directly; no further auth needed, the URL is already signed


class DocumentStatusOut(BaseModel):
    status: DocumentStatus


class DocumentOut(BaseModel):
    id: uuid.UUID
    type: DocumentType
    child_id: uuid.UUID | None
    status: DocumentStatus


@router.get("/mine")
def list_my_documents(
    profile: CurrentProfile, db: DbSession, type: DocumentType | None = None, child_id: uuid.UUID | None = None
) -> list[DocumentOut]:
    """So a parent or sitter can see "uploaded" / "being checked" / "please try again" for their own
    files -- not a signed view URL, which stays admin-only."""
    rows = documents.list_mine(db, profile.id, type, child_id)
    return [DocumentOut(id=row.id, type=row.type, child_id=row.child_id, status=row.status) for row in rows]


@router.post("/upload-url", status_code=201)
def create_upload_url(body: RequestUpload, profile: CurrentProfile, db: DbSession, storage: Storage) -> UploadTicket:
    ticket = documents.request_upload(db, storage, profile.id, body.type, body.child_id)
    return UploadTicket(document_id=ticket.document_id, upload_url=ticket.upload_url)


@router.post("/{document_id}/confirm")
def confirm_upload(
    document_id: uuid.UUID, profile: CurrentProfile, db: DbSession, storage: Storage
) -> DocumentStatusOut:
    document = documents.confirm_upload(db, storage, profile.id, document_id)
    return DocumentStatusOut(status=document.status)
