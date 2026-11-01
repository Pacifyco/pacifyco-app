from functools import lru_cache

from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase

# Fixed constraint names so Alembic migrations are predictable and reversible.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def sqlalchemy_url(url: str) -> str:
    """Use psycopg 3 for plain Postgres URLs, as copied from Supabase (postgresql://... or postgres://...)."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url


# The database role the API runs as when deployed (created by the "api database role" migration).
API_ROLE = "pacifyco_api"


@lru_cache
def engine_for(url: str) -> Engine:
    """One connection pool per database URL, kept small for Supabase's session pooler."""
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5, connect_args={"connect_timeout": 5})
