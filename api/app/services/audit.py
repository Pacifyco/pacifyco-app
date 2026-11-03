"""State changes on bookings, payouts, strikes and verifications (CLAUDE.md 5). Append-only; the
caller commits, same convention as `app.services.legal`."""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def record(
    db: Session,
    actor_id: uuid.UUID | None,
    action: str,
    entity: str,
    entity_id: str,
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    db.add(AuditLog(actor_id=actor_id, action=action, entity=entity, entity_id=entity_id, before=before, after=after))
