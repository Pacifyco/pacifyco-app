"""The Emergency and Issues buttons (CLAUDE.md 6.9; phase 8).

Both are on a booking from its start until 1 hour after its end or check-out, whichever is later, for a
confirmed, in-progress or just-completed booking (Reuben, 2026-11-21).

- Emergency: the parent picks Emergency (safety or medical), Theft or Abuse; the sitter picks Emergency or
  "I'm being abused or feel unsafe" (Reuben, 2026-11-21). Every admin is emailed at once and it shows at the
  top of the admin panel until acknowledged. A parent's theft or abuse report suspends the sitter at once,
  until an admin resolves it and decides whether she comes back. An open incident holds her payout for that
  booking (`has_open_incident`, used by payouts in phase 9).
- Issues: a non-emergency issue (running late, something else), a complaint linked to the booking, emailed
  to admins; admins mark it replied and resolved (the full complaints process, 6.12, comes later).
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import (
    Booking,
    BookingStatus,
    Complaint,
    ComplaintStatus,
    ComplaintType,
    Incident,
    IncidentKind,
    IncidentStatus,
    IssueTopic,
    Profile,
    ProfileStatus,
    Role,
)
from app.services import audit, earnings

AFTER_END = timedelta(hours=1)
OPEN_TO = (BookingStatus.confirmed, BookingStatus.in_progress, BookingStatus.completed)
PARENT_KINDS = (IncidentKind.emergency, IncidentKind.theft, IncidentKind.abuse)
SITTER_KINDS = (IncidentKind.emergency, IncidentKind.sitter_unsafe)
SUSPENDS = (IncidentKind.theft, IncidentKind.abuse)  # a parent's report about the sitter


def window_ends(booking: Booking) -> datetime:
    end = booking.ends_at
    if booking.checked_out_at is not None and booking.checked_out_at > end:
        end = booking.checked_out_at
    return end + AFTER_END


def buttons_open(booking: Booking, now: datetime) -> bool:
    """Whether the Emergency and Issues buttons are on this booking now."""
    return booking.status in OPEN_TO and booking.starts_at <= now <= window_ends(booking)


def _their_booking(db: Session, person: Profile, booking_id: uuid.UUID, now: datetime) -> Booking:
    column = Booking.parent_id if person.role == Role.parent else Booking.sitter_id
    booking = db.scalar(select(Booking).where(Booking.id == booking_id, column == person.id))
    if booking is None:
        raise AppError(404, "not_found", "We couldn't find that booking.")
    if not buttons_open(booking, now):
        raise AppError(
            409,
            "not_during_booking",
            "This is for during a booking. For anything else, please contact Pacifyco on +91 8848873841.",
        )
    return booking


def _clean(note: str | None) -> str | None:
    note = (note or "").strip()
    return note or None


def raise_emergency(
    db: Session, person: Profile, booking_id: uuid.UUID, kind: IncidentKind, note: str | None, now: datetime
) -> Incident:
    allowed = PARENT_KINDS if person.role == Role.parent else SITTER_KINDS
    if kind not in allowed:
        raise AppError(422, "invalid_kind", "Please choose what's happening.")
    booking = _their_booking(db, person, booking_id, now)
    incident = Incident(booking_id=booking.id, raised_by=person.id, kind=kind, note=_clean(note), created_at=now)
    db.add(incident)
    db.flush()
    audit.record(
        db,
        person.id,
        "incident_raised",
        "incident",
        str(incident.id),
        after={"booking_id": str(booking.id), "kind": kind.value},
    )
    if person.role == Role.parent and kind in SUSPENDS:
        sitter = db.scalar(select(Profile).where(Profile.id == booking.sitter_id).with_for_update())
        assert sitter is not None
        if sitter.status == ProfileStatus.active:
            audit.record(
                db,
                None,
                "sitter_suspended",
                "profiles",
                str(sitter.id),
                before={"status": sitter.status.value},
                after={"status": ProfileStatus.suspended.value, "incident_id": str(incident.id)},
            )
            sitter.status = ProfileStatus.suspended
            incident.suspended_sitter = True
    earnings.hold(db, booking.id)  # an open incident holds her pay for this booking (6.9)
    db.commit()
    return incident


def _incident(db: Session, incident_id: uuid.UUID) -> Incident:
    incident = db.scalar(select(Incident).where(Incident.id == incident_id).with_for_update())
    if incident is None:
        raise AppError(404, "not_found", "We couldn't find that incident.")
    return incident


def acknowledge(db: Session, admin_id: uuid.UUID, incident_id: uuid.UUID, now: datetime) -> Incident:
    """An admin has seen it and is calling both people: the alert at the top of the panel goes."""
    incident = _incident(db, incident_id)
    if incident.status != IncidentStatus.open:
        return incident
    incident.status = IncidentStatus.acknowledged
    incident.acknowledged_by = admin_id
    incident.acknowledged_at = now
    audit.record(db, admin_id, "incident_acknowledged", "incident", str(incident.id), after={"status": "acknowledged"})
    db.commit()
    return incident


def resolve(
    db: Session, admin_id: uuid.UUID, incident_id: uuid.UUID, note: str, reinstate_sitter: bool, now: datetime
) -> Incident:
    """Closed with what happened. If the report suspended the sitter, the admin decides whether she comes
    back (a confirmed theft normally ends in removal, 6.9, which is a separate decision)."""
    incident = _incident(db, incident_id)
    if incident.status == IncidentStatus.resolved:
        raise AppError(409, "already_resolved", "This incident has already been resolved.")
    if incident.acknowledged_at is None:
        incident.acknowledged_by = admin_id
        incident.acknowledged_at = now
    incident.status = IncidentStatus.resolved
    incident.resolved_by = admin_id
    incident.resolved_at = now
    incident.resolution_note = note
    reinstated = False
    if incident.suspended_sitter and reinstate_sitter:
        booking = db.get(Booking, incident.booking_id)
        assert booking is not None
        sitter = db.scalar(select(Profile).where(Profile.id == booking.sitter_id).with_for_update())
        assert sitter is not None
        if sitter.status == ProfileStatus.suspended:
            audit.record(
                db,
                admin_id,
                "sitter_reinstated",
                "profiles",
                str(sitter.id),
                before={"status": sitter.status.value},
                after={"status": ProfileStatus.active.value, "incident_id": str(incident.id)},
            )
            sitter.status = ProfileStatus.active
            reinstated = True
    audit.record(
        db,
        admin_id,
        "incident_resolved",
        "incident",
        str(incident.id),
        after={"status": "resolved", "note": note, "sitter_reinstated": reinstated},
    )
    earnings.release_booking(db, incident.booking_id, now)
    db.commit()
    return incident


def open_incidents(db: Session) -> list[Incident]:
    """Not yet resolved, newest first: open ones need acknowledging, acknowledged ones resolving."""
    return list(
        db.scalars(
            select(Incident).where(Incident.status != IncidentStatus.resolved).order_by(Incident.created_at.desc())
        )
    )


def has_open_incident(db: Session, booking_id: uuid.UUID) -> bool:
    """An open incident holds the sitter's payout for this booking (6.9; payouts, phase 9)."""
    return (
        db.scalar(
            select(Incident.id).where(Incident.booking_id == booking_id, Incident.status != IncidentStatus.resolved)
        )
        is not None
    )


def latest_incident(db: Session, booking_id: uuid.UUID) -> Incident | None:
    return db.scalar(select(Incident).where(Incident.booking_id == booking_id).order_by(Incident.created_at.desc()))


# ---------- issues: non-emergency, a complaint linked to the booking ----------

TOPIC_WORDS = {IssueTopic.running_late: "Running late", IssueTopic.other: "Something else"}


def raise_issue(
    db: Session, person: Profile, booking_id: uuid.UUID, topic: IssueTopic, note: str | None, now: datetime
) -> Complaint:
    booking = _their_booking(db, person, booking_id, now)
    note = _clean(note)
    if topic == IssueTopic.other and note is None:
        raise AppError(422, "note_needed", "Please tell us what's wrong.")
    complaint = Complaint(
        raised_by=person.id,
        booking_id=booking.id,
        type=ComplaintType.booking,
        topic=topic,
        description=note or TOPIC_WORDS[topic],
        created_at=now,
    )
    db.add(complaint)
    db.flush()
    audit.record(
        db,
        person.id,
        "complaint_raised",
        "complaint",
        str(complaint.id),
        after={"booking_id": str(booking.id), "topic": topic.value},
    )
    db.commit()
    return complaint


def open_issues(db: Session) -> list[Complaint]:
    return list(
        db.scalars(
            select(Complaint)
            .where(Complaint.status.in_((ComplaintStatus.open, ComplaintStatus.replied)))
            .order_by(Complaint.created_at)
        )
    )


def update_issue(
    db: Session, admin_id: uuid.UUID, complaint_id: uuid.UUID, to: ComplaintStatus, now: datetime
) -> Complaint:
    """Replied (an admin has been in touch) or resolved."""
    complaint = db.scalar(select(Complaint).where(Complaint.id == complaint_id).with_for_update())
    if complaint is None:
        raise AppError(404, "not_found", "We couldn't find that issue.")
    if complaint.status == ComplaintStatus.resolved:
        raise AppError(409, "already_resolved", "This issue has already been resolved.")
    before = complaint.status.value
    if complaint.first_reply_at is None:
        complaint.first_reply_at = now
    if to == ComplaintStatus.resolved:
        complaint.resolved_at = now
        complaint.decided_by = admin_id
    complaint.status = to
    audit.record(
        db,
        admin_id,
        "complaint_updated",
        "complaint",
        str(complaint.id),
        before={"status": before},
        after={"status": to.value},
    )
    db.commit()
    return complaint
