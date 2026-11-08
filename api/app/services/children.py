"""A parent's children (CLAUDE.md sections 6.4 and 8). Adding a child never checks their age --
that only matters when booking care for them (phase 7) -- so even a newborn can be added here."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Child, Document, Parent, VerificationStatus
from app.services import audit


def list_children(db: Session, parent_id: uuid.UUID) -> list[Child]:
    return list(db.scalars(select(Child).where(Child.parent_id == parent_id).order_by(Child.id)))


def add_child(
    db: Session,
    parent_id: uuid.UUID,
    name: str,
    date_of_birth: date,
    allergies: str | None,
    medical_notes: str | None,
    routines: str | None,
) -> Child:
    child = Child(
        parent_id=parent_id,
        name=name,
        date_of_birth=date_of_birth,
        allergies=allergies,
        medical_notes=medical_notes,
        routines=routines,
    )
    db.add(child)
    # A verified family adding a child waits again until that child's birth certificate is approved
    # (CLAUDE.md 7). The other children stay verified.
    parent = db.get(Parent, parent_id)
    if parent is not None and parent.verification_status == VerificationStatus.approved:
        parent.verification_status = VerificationStatus.pending
        audit.record(
            db,
            parent_id,
            "parent_verification_reset",
            "parents",
            str(parent_id),
            before={"verification_status": "approved"},
            after={"verification_status": "pending"},
        )
    db.commit()
    return child


def _owned_child(db: Session, parent_id: uuid.UUID, child_id: uuid.UUID) -> Child:
    child = db.get(Child, child_id)
    if child is None:
        raise AppError(404, "not_found", "That child isn't on your family's list")
    if child.parent_id != parent_id:  # no IDOR: can't touch another family's child
        raise AppError(403, "forbidden", "That child isn't on your family's list")
    return child


def update_child(
    db: Session,
    parent_id: uuid.UUID,
    child_id: uuid.UUID,
    name: str,
    date_of_birth: date,
    allergies: str | None,
    medical_notes: str | None,
    routines: str | None,
) -> Child:
    child = _owned_child(db, parent_id, child_id)
    verified = child.verification_status == VerificationStatus.approved
    if verified and (name != child.name or date_of_birth != child.date_of_birth):
        # Checked against a birth certificate that's since been deleted; only Pacify can change them.
        raise AppError(
            409,
            "child_verified",
            "This child's name and date of birth are verified. Please contact Pacify to change them.",
        )
    child.name = name
    child.date_of_birth = date_of_birth
    child.allergies = allergies
    child.medical_notes = medical_notes
    child.routines = routines
    db.commit()
    return child


def remove_child(db: Session, parent_id: uuid.UUID, child_id: uuid.UUID) -> None:
    child = _owned_child(db, parent_id, child_id)
    if db.scalar(select(Document.id).where(Document.child_id == child_id).limit(1)) is not None:
        # documents.child_id is ON DELETE RESTRICT; refuse cleanly instead of a raw database error.
        raise AppError(409, "child_has_documents", "This child has documents on file. Please contact Pacify.")
    db.delete(child)
    db.commit()
