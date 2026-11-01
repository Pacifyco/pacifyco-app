import os
from typing import Annotated

import sentry_sdk
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import API_ROLE, engine_for
from app.errors import AppError
from app.settings import Settings, get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
    """Liveness check for Render. Doesn't touch the database, so a paused staging database
    doesn't make Render restart the service. `commit` shows which code is running (Render sets
    RENDER_GIT_COMMIT on each deploy; the repository is public, so this reveals nothing new)."""
    commit = os.environ.get("RENDER_GIT_COMMIT", "")[:7] or "local"
    return {"status": "ok", "environment": settings.environment, "commit": commit}


@router.get("/health/db")
def health_db(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str | bool]:
    """Checks the API can sign in to its database, and whether it signed in as its own limited role.
    Not used by Render's health check."""
    try:
        with engine_for(settings.effective_database_url).connect() as conn:
            role = conn.execute(text("SELECT current_user")).scalar_one()
    except SQLAlchemyError as exc:
        sentry_sdk.capture_exception(exc)  # the details go to Sentry, never into the response
        raise AppError(503, "database_unavailable", "The database isn't reachable right now") from exc
    return {"status": "ok", "database": "ok", "api_role": role == API_ROLE}
