"""The admin area. Every route here is for admins only (CLAUDE.md 9: wrong role gets 403)."""

from fastapi import APIRouter, Depends

from app.auth import require_role
from app.models import Role

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role(Role.admin))])
