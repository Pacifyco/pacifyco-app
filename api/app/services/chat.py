"""Chat between a parent and a sitter (CLAUDE.md 6.11; phase 8).

- A conversation exists once they've had a confirmed booking (no messaging before booking).
- New messages can be sent while they have a booking that is confirmed, in progress or still to come, and for
  24 hours after their last booking ends (Reuben, 2026-11-21). After that it's read-only until they book again.
- Admins read a chat only when handling an incident, and every read is audit logged.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Booking, BookingStatus, Incident, Message, Profile, Role
from app.models.messages import MAX_MESSAGE_LENGTH
from app.services import audit

OPEN_AFTER_LAST = timedelta(hours=24)
# Bookings that went ahead, or are on their way: they open a chat. (Requests, unpaid ones and those cancelled
# before they were confirmed don't.)
OPENS_CHAT = (
    BookingStatus.confirmed,
    BookingStatus.in_progress,
    BookingStatus.completed,
    BookingStatus.closed_by_admin,
    BookingStatus.parent_absent,
    BookingStatus.sitter_no_show,
    BookingStatus.declined_man_at_home,
    BookingStatus.child_under_age,
    BookingStatus.sitter_left_unsafe,
)
CURRENT = (BookingStatus.confirmed, BookingStatus.in_progress)


def _pair(person: Profile, other_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """(parent_id, sitter_id) for this person and the other side."""
    return (person.id, other_id) if person.role == Role.parent else (other_id, person.id)


def _pair_bookings(parent_id: uuid.UUID, sitter_id: uuid.UUID):
    return and_(Booking.parent_id == parent_id, Booking.sitter_id == sitter_id, Booking.status.in_(OPENS_CHAT))


def exists(db: Session, parent_id: uuid.UUID, sitter_id: uuid.UUID) -> bool:
    return db.scalar(select(Booking.id).where(_pair_bookings(parent_id, sitter_id)).limit(1)) is not None


def can_send(db: Session, parent_id: uuid.UUID, sitter_id: uuid.UUID, now: datetime) -> bool:
    """A booking now or to come, or one that ended in the last 24 hours."""
    found = db.scalar(
        select(Booking.id)
        .where(
            _pair_bookings(parent_id, sitter_id),
            or_(Booking.status.in_(CURRENT), Booking.ends_at > now - OPEN_AFTER_LAST),
        )
        .limit(1)
    )
    return found is not None


def _conversation(db: Session, person: Profile, other_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    parent_id, sitter_id = _pair(person, other_id)
    if not exists(db, parent_id, sitter_id):
        raise AppError(404, "not_found", "You can message each other once you have a confirmed booking together.")
    return parent_id, sitter_id


def messages(db: Session, parent_id: uuid.UUID, sitter_id: uuid.UUID, after: datetime | None = None) -> list[Message]:
    query = select(Message).where(Message.parent_id == parent_id, Message.sitter_id == sitter_id)
    if after is not None:
        query = query.where(Message.created_at > after)
    return list(db.scalars(query.order_by(Message.created_at, Message.id)))


@dataclass(frozen=True)
class Conversation:
    parent_id: uuid.UUID
    sitter_id: uuid.UUID
    messages: list[Message]
    can_send: bool


def read(
    db: Session, person: Profile, other_id: uuid.UUID, now: datetime, after: datetime | None = None
) -> Conversation:
    parent_id, sitter_id = _conversation(db, person, other_id)
    return Conversation(
        parent_id, sitter_id, messages(db, parent_id, sitter_id, after), can_send(db, parent_id, sitter_id, now)
    )


def send(db: Session, person: Profile, other_id: uuid.UUID, body: str, now: datetime) -> Message:
    parent_id, sitter_id = _conversation(db, person, other_id)
    body = body.strip()
    if not body:
        raise AppError(422, "empty_message", "Please write a message.")
    if len(body) > MAX_MESSAGE_LENGTH:
        raise AppError(422, "message_too_long", f"Please keep a message under {MAX_MESSAGE_LENGTH} characters.")
    if not can_send(db, parent_id, sitter_id, now):
        raise AppError(
            409, "chat_closed", "This chat is closed. It opens again when you have another booking together."
        )
    message = Message(parent_id=parent_id, sitter_id=sitter_id, sender_id=person.id, body=body, created_at=now)
    db.add(message)
    db.commit()
    return message


@dataclass(frozen=True)
class Summary:
    other_id: uuid.UUID
    other_name: str | None
    last_body: str | None
    last_at: datetime | None
    last_from_me: bool
    can_send: bool


def conversations(db: Session, person: Profile, now: datetime) -> list[Summary]:
    """Everyone this person can chat with (or has), the most recent message first."""
    mine, theirs = (
        (Booking.parent_id, Booking.sitter_id) if person.role == Role.parent else (Booking.sitter_id, Booking.parent_id)
    )
    others = list(db.scalars(select(theirs).where(mine == person.id, Booking.status.in_(OPENS_CHAT)).distinct()))
    found = []
    for other_id in others:
        parent_id, sitter_id = _pair(person, other_id)
        last = db.scalar(
            select(Message)
            .where(Message.parent_id == parent_id, Message.sitter_id == sitter_id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        other = db.get(Profile, other_id)
        found.append(
            Summary(
                other_id=other_id,
                other_name=other.full_name if other else None,
                last_body=last.body if last else None,
                last_at=last.created_at if last else None,
                last_from_me=bool(last and last.sender_id == person.id),
                can_send=can_send(db, parent_id, sitter_id, now),
            )
        )
    return sorted(found, key=lambda item: (item.last_at is None, -(item.last_at.timestamp() if item.last_at else 0)))


def read_for_incident(db: Session, admin_id: uuid.UUID, incident_id: uuid.UUID) -> list[Message]:
    """An admin reads the chat between the incident's parent and sitter (6.11), audit logged."""
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise AppError(404, "not_found", "We couldn't find that incident.")
    booking = db.get(Booking, incident.booking_id)
    assert booking is not None
    found = messages(db, booking.parent_id, booking.sitter_id)
    audit.record(
        db,
        admin_id,
        "chat_read_by_admin",
        "incident",
        str(incident.id),
        after={"parent_id": str(booking.parent_id), "sitter_id": str(booking.sitter_id), "messages": len(found)},
    )
    db.commit()
    return found
