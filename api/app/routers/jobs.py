import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header

from app.db import engine_for
from app.errors import AppError
from app.services.jobs import RUNS
from app.settings import Settings, get_settings

router = APIRouter(prefix="/internal/jobs", tags=["jobs"])


def require_jobs_secret(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Only the scheduler, which sends `Authorization: Bearer <JOBS_SECRET>`, may run jobs. With no
    JOBS_SECRET configured nobody can (fail closed)."""
    expected = f"Bearer {settings.jobs_secret}".encode()
    supplied = (authorization or "").encode()
    if not settings.jobs_secret or not hmac.compare_digest(supplied, expected):
        raise AppError(401, "unauthorized", "Not allowed")


@router.post("/{run}", dependencies=[Depends(require_jobs_secret)])
def run_jobs(run: str, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, object]:
    tasks = RUNS.get(run)
    if tasks is None:
        raise AppError(404, "unknown_job", "No such job run")
    # One transaction per task, so a failing task doesn't undo the ones before it.
    ran = []
    engine = engine_for(settings.effective_database_url)
    for name, task in tasks:
        with engine.begin() as conn:
            task(conn)
        ran.append(name)
    return {"run": run, "ran": ran}
