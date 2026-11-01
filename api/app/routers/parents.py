"""The parent area. Every route here is for parents only (CLAUDE.md 9: wrong role gets 403)."""

from fastapi import APIRouter, Depends

from app.auth import require_role
from app.models import Role

router = APIRouter(prefix="/parent", tags=["parent"], dependencies=[Depends(require_role(Role.parent))])
