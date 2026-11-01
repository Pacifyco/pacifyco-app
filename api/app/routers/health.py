from typing import Annotated

from fastapi import APIRouter, Depends

from app.settings import Settings, get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
    """Liveness check for Render. Doesn't touch the database, so a paused staging database
    doesn't make Render restart the service."""
    return {"status": "ok", "environment": settings.environment}
