"""Removes every parent and sitter account from a **staging** database, so test emails can sign up
again fresh (Reuben, 2026-11-13). Admins are kept. Never for production: the CLI refuses when
ENVIRONMENT is production, and real records there are never removed this way.

Run as the database owner (the API's own role can't delete from the append-only tables). Everything in
the database goes in one transaction; the stored files and the Supabase sign-in accounts are removed
after it commits, and anything that couldn't be removed is reported.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Child,
    Consent,
    Document,
    DocumentAccessLog,
    LegalAcceptance,
    Profile,
    PsychAttempt,
    Reference,
    Role,
)


@dataclass
class Found:
    """What a reset would remove."""

    profile_ids: list[uuid.UUID]
    parents: int
    sitters: int
    children: int
    documents: int
    storage_paths: list[str] = field(default_factory=list)


def find(db: Session) -> Found:
    profiles = list(db.execute(select(Profile.id, Profile.role).where(Profile.role.in_([Role.parent, Role.sitter]))))
    ids = [row.id for row in profiles]
    children = db.scalars(select(Child.id).where(Child.parent_id.in_(ids))).all()
    documents = db.execute(
        select(Document.id, Document.storage_path, Document.deleted_at).where(Document.owner_profile_id.in_(ids))
    ).all()
    return Found(
        profile_ids=ids,
        parents=sum(1 for row in profiles if row.role == Role.parent),
        sitters=sum(1 for row in profiles if row.role == Role.sitter),
        children=len(children),
        documents=len(documents),
        storage_paths=[row.storage_path for row in documents if row.deleted_at is None],
    )


def delete_all(db: Session, found: Found) -> None:
    """Deletes every row belonging to these parents and sitters, then their profiles (which cascade to
    parents, children, contacts, sitters, references, steps, availability and psych attempts)."""
    ids = found.profile_ids
    if not ids:
        return
    child_ids = db.scalars(select(Child.id).where(Child.parent_id.in_(ids))).all()
    document_ids = db.scalars(select(Document.id).where(Document.owner_profile_id.in_(ids))).all()
    reference_ids = db.scalars(select(Reference.id).where(Reference.sitter_id.in_(ids))).all()
    attempt_ids = db.scalars(select(PsychAttempt.id).where(PsychAttempt.sitter_id.in_(ids))).all()
    # Audit rows they made, and rows about them or their records (entity ids are stored as text).
    about = [str(item) for item in [*ids, *child_ids, *document_ids, *reference_ids, *attempt_ids]]

    db.execute(delete(DocumentAccessLog).where(DocumentAccessLog.document_id.in_(document_ids)))
    db.execute(delete(Document).where(Document.id.in_(document_ids)))
    db.execute(delete(Consent).where(Consent.parent_id.in_(ids)))
    db.execute(delete(LegalAcceptance).where(LegalAcceptance.profile_id.in_(ids)))
    db.execute(delete(AuditLog).where(or_(AuditLog.actor_id.in_(ids), AuditLog.entity_id.in_(about))))
    db.execute(delete(Profile).where(Profile.id.in_(ids)))
    db.commit()
