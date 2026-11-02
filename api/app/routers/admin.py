"""The admin area. Every route here is for admins only (CLAUDE.md 9: wrong role gets 403)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import require_role
from app.deps import DbSession
from app.models import Profile, Role
from app.services import documents
from app.services.storage import StorageClient, get_storage

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role(Role.admin))])
Admin = Annotated[Profile, Depends(require_role(Role.admin))]
Storage = Annotated[StorageClient, Depends(get_storage)]


class DocumentViewUrl(BaseModel):
    url: str


@router.get("/documents/{document_id}/view-url")
def document_view_url(document_id: uuid.UUID, admin: Admin, db: DbSession, storage: Storage) -> DocumentViewUrl:
    """A short-lived signed URL to view one document. Every call is logged (CLAUDE.md 5)."""
    return DocumentViewUrl(url=documents.get_view_url(db, storage, admin.id, document_id))
