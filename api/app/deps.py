from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db import engine_for
from app.settings import Settings, get_settings


def get_db(settings: Annotated[Settings, Depends(get_settings)]) -> Iterator[Session]:
    """One database session per request. Routers commit their own writes."""
    with Session(engine_for(settings.effective_database_url)) as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]
