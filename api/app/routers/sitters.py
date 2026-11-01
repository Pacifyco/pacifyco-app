"""The sitter area. Every route here is for sitters only (CLAUDE.md 9: wrong role gets 403)."""

from fastapi import APIRouter, Depends

from app.auth import require_role
from app.models import Role

router = APIRouter(prefix="/sitter", tags=["sitter"], dependencies=[Depends(require_role(Role.sitter))])
