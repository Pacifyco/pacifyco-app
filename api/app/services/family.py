"""Emergency contacts and authorised adults (CLAUDE.md section 7, Family Terms 2.5): two emergency
contacts per family, not per child, and any number of named adults who may hand over or receive a
child during a booking. Getting each person's permission to share their details is the parent's own
responsibility (the web asks them to confirm it before saving); nothing about that confirmation is
recorded here. Field validation (name, relationship, a real Indian mobile number, exactly one
contact) happens in the router's request schema, same as sign-up; this module trusts its input."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import AuthorisedAdult, EmergencyContact


def list_emergency_contacts(db: Session, parent_id: uuid.UUID) -> list[EmergencyContact]:
    return list(
        db.scalars(
            select(EmergencyContact).where(EmergencyContact.parent_id == parent_id).order_by(EmergencyContact.id)
        )
    )


def set_emergency_contacts(
    db: Session, parent_id: uuid.UUID, contacts: list[tuple[str, str, str]]
) -> list[EmergencyContact]:
    """Replaces both at once, so the family never has a half-saved set. `contacts` is (name,
    relationship, phone) tuples; the caller has already checked how many there are."""
    db.execute(delete(EmergencyContact).where(EmergencyContact.parent_id == parent_id))
    db.add_all(
        [
            EmergencyContact(parent_id=parent_id, name=name, relationship=rel, phone=phone)
            for name, rel, phone in contacts
        ]
    )
    db.commit()
    return list_emergency_contacts(db, parent_id)


def list_authorised_adults(db: Session, parent_id: uuid.UUID) -> list[AuthorisedAdult]:
    return list(
        db.scalars(select(AuthorisedAdult).where(AuthorisedAdult.parent_id == parent_id).order_by(AuthorisedAdult.id))
    )


def add_authorised_adult(
    db: Session, parent_id: uuid.UUID, name: str, relationship: str, phone: str
) -> AuthorisedAdult:
    adult = AuthorisedAdult(parent_id=parent_id, name=name, relationship=relationship, phone=phone)
    db.add(adult)
    db.commit()
    return adult


def remove_authorised_adult(db: Session, parent_id: uuid.UUID, adult_id: uuid.UUID) -> None:
    adult = db.get(AuthorisedAdult, adult_id)
    if adult is None:
        raise AppError(404, "not_found", "That person isn't on your list")
    if adult.parent_id != parent_id:  # no IDOR: can't remove another family's adult
        raise AppError(403, "forbidden", "That person isn't on your list")
    db.delete(adult)
    db.commit()
