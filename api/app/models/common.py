import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, func, text
from sqlalchemy.orm import Mapped, mapped_column


def enum_column(enum_cls: type[StrEnum], name: str):
    """Stored as text with a CHECK constraint (not a Postgres enum), so values are easy to add later."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda cls: [member.value for member in cls],
        validate_strings=True,
    )


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))


def created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class VerificationStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
