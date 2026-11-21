"""Chat between a parent and a sitter (CLAUDE.md 6.11; phase 8).

One conversation per parent and sitter. It opens once they have a confirmed booking, and new messages can
be sent while they have one confirmed, in progress or still to come, and for 24 hours after their last
booking ends (Reuben, 2026-11-21); after that it's read-only until they book again. The app polls every
10 seconds while a chat is open (no websockets). Admins can read a chat when handling an incident, and every
read is audit logged. Sitters never have to share their phone number; the app doesn't stop them choosing to.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import created_at, uuid_pk

MAX_MESSAGE_LENGTH = 2000


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(f"char_length(body) BETWEEN 1 AND {MAX_MESSAGE_LENGTH}", name="body_length"),
        CheckConstraint("sender_id = parent_id OR sender_id = sitter_id", name="sender_in_conversation"),
        Index("ix_messages_parent_id_sitter_id_created_at", "parent_id", "sitter_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    parent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    sitter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()
