"""The audit log and the document access log, for admins (phase 10; CLAUDE.md 5).

Both logs are append-only (the API's role can only add rows), so these are read-only views: newest first,
50 at a time, with filters. Admins already see everything the rows hold (statuses, reasons, references), and
neither log holds bank details, health details or document contents.

- **Audit log:** every state change (actor, action, record, before and after). Filter by who did it (an
  admin, or the rules when there's no actor), the kind of record, one record's id, words in the action and
  India dates. A row about a person (a profile, sitter or parent) carries their name and role, so it links to
  their admin page; a row about a booking links to its page.
- **Document access log:** every time an admin opened a document: who, which document, whose and when.
  Filter by the admin, the document type, the owner's name and India dates.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, aliased

from app.models import AuditLog, Child, Document, DocumentAccessLog, DocumentType, Profile, Role
from app.services.availability import INDIA

PAGE_SIZE = 50
TEXT_MAX = 100
PERSON_ENTITIES = ("profiles", "sitters", "parents")  # rows whose entity_id is a person's profile id


@dataclass
class Person:
    id: uuid.UUID
    name: str | None
    role: Role


@dataclass
class AuditEntry:
    row: AuditLog
    actor_name: str | None
    person: Person | None  # who the row is about, when it's about a person


@dataclass
class DocumentView:
    row: DocumentAccessLog
    admin_name: str | None
    document: Document
    owner: Person
    child_name: str | None


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _on_dates(query: Select, column, on_from: date | None, on_to: date | None) -> Select:
    """India dates, both inclusive."""
    if on_from is not None:
        query = query.where(column >= datetime.combine(on_from, time(), INDIA))
    if on_to is not None:
        query = query.where(column < datetime.combine(on_to + timedelta(days=1), time(), INDIA))
    return query


def _uuid(text: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(text)
    except ValueError:
        return None


def admins(db: Session) -> list[tuple[uuid.UUID, str | None]]:
    """Every admin, for the "who did it" filters."""
    return list(db.execute(select(Profile.id, Profile.full_name).where(Profile.role == Role.admin)).all())


def audit_entries(
    db: Session,
    *,
    actor_id: uuid.UUID | None = None,
    by_rules: bool = False,
    entity: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    on_from: date | None = None,
    on_to: date | None = None,
    page: int = 0,
) -> tuple[list[AuditEntry], bool]:
    """Audit rows, newest first, a page at a time; and whether there are more."""
    query = select(AuditLog, Profile.full_name).outerjoin(Profile, Profile.id == AuditLog.actor_id)
    if by_rules:
        query = query.where(AuditLog.actor_id.is_(None))
    elif actor_id is not None:
        query = query.where(AuditLog.actor_id == actor_id)
    if entity:
        query = query.where(AuditLog.entity == entity[:TEXT_MAX])
    if entity_id and entity_id.strip():
        query = query.where(AuditLog.entity_id == entity_id.strip()[:TEXT_MAX])
    words = (action or "").strip()[:TEXT_MAX]
    if words:
        query = query.where(AuditLog.action.ilike(_like(words.replace(" ", "_")), escape="\\"))
    query = _on_dates(query, AuditLog.created_at, on_from, on_to)
    found = db.execute(query.order_by(AuditLog.id.desc()).offset(max(page, 0) * PAGE_SIZE).limit(PAGE_SIZE + 1)).all()
    rows = found[:PAGE_SIZE]
    about = {key for row, _ in rows if row.entity in PERSON_ENTITIES and (key := _uuid(row.entity_id)) is not None}
    people = {
        person.id: Person(person.id, person.full_name, person.role)
        for person in (db.scalars(select(Profile).where(Profile.id.in_(about))) if about else [])
    }
    entries = [
        AuditEntry(row, name, people.get(_uuid(row.entity_id)) if row.entity in PERSON_ENTITIES else None)
        for row, name in rows
    ]
    return entries, len(found) > PAGE_SIZE


def document_views(
    db: Session,
    *,
    admin_id: uuid.UUID | None = None,
    document_type: DocumentType | None = None,
    owner: str | None = None,
    owner_id: uuid.UUID | None = None,
    on_from: date | None = None,
    on_to: date | None = None,
    page: int = 0,
) -> tuple[list[DocumentView], bool]:
    """Admins' views of documents, newest first, a page at a time; and whether there are more."""
    admin = aliased(Profile)
    holder = aliased(Profile)
    query = (
        select(DocumentAccessLog, admin.full_name, Document, holder, Child.name)
        .join(Document, Document.id == DocumentAccessLog.document_id)
        .join(holder, holder.id == Document.owner_profile_id)
        .outerjoin(admin, admin.id == DocumentAccessLog.admin_id)
        .outerjoin(Child, Child.id == Document.child_id)
    )
    if admin_id is not None:
        query = query.where(DocumentAccessLog.admin_id == admin_id)
    if document_type is not None:
        query = query.where(Document.type == document_type)
    if owner_id is not None:
        query = query.where(Document.owner_profile_id == owner_id)
    name = (owner or "").strip()[:TEXT_MAX]
    if name:
        query = query.where(holder.full_name.ilike(_like(name), escape="\\"))
    query = _on_dates(query, DocumentAccessLog.accessed_at, on_from, on_to)
    found = db.execute(
        query.order_by(DocumentAccessLog.id.desc()).offset(max(page, 0) * PAGE_SIZE).limit(PAGE_SIZE + 1)
    ).all()
    views = [
        DocumentView(row, admin_name, document, Person(person.id, person.full_name, person.role), child_name)
        for row, admin_name, document, person, child_name in found[:PAGE_SIZE]
    ]
    return views, len(found) > PAGE_SIZE
