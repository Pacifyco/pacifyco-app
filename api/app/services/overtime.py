"""Overtime requests (CLAUDE.md 6.8; phase 8). During the booking the parent asks for extra whole hours;
the sitter accepts or declines once they've agreed it between them. Nothing is charged here -- overtime
is always worked out at check-out, whether or not a request was ever made or accepted, and a parent who's
simply running late with no accepted request still owes it."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Booking, BookingStatus, OvertimeRequest, OvertimeRequestStatus
from app.services import audit


def _booking(db: Session, booking_id: uuid.UUID, **owner: uuid.UUID) -> Booking:
    query = select(Booking).where(Booking.id == booking_id)
    for column, value in owner.items():
        query = query.where(getattr(Booking, column) == value)
    booking = db.scalar(query.with_for_update())
    if booking is None:
        raise AppError(404, "not_found", "We couldn't find that booking.")
    return booking


def for_booking(db: Session, booking_id: uuid.UUID) -> OvertimeRequest | None:
    """The booking's latest overtime request, if any."""
    return db.scalar(
        select(OvertimeRequest)
        .where(OvertimeRequest.booking_id == booking_id)
        .order_by(OvertimeRequest.requested_at.desc())
    )


def request(db: Session, parent_id: uuid.UUID, booking_id: uuid.UUID, hours: int, now: datetime) -> OvertimeRequest:
    """The parent asks for extra whole hours, only while the booking is under way (6.8)."""
    booking = _booking(db, booking_id, parent_id=parent_id)
    if booking.status != BookingStatus.in_progress:
        raise AppError(409, "not_now", "You can request overtime once the booking has started.")
    open_request = db.scalar(
        select(OvertimeRequest.id).where(
            OvertimeRequest.booking_id == booking.id, OvertimeRequest.status == OvertimeRequestStatus.pending
        )
    )
    if open_request is not None:
        raise AppError(409, "already_requested", "There's already a request waiting for her answer.")
    overtime_request = OvertimeRequest(booking_id=booking.id, requested_hours=hours, requested_at=now)
    db.add(overtime_request)
    db.flush()
    audit.record(
        db,
        parent_id,
        "overtime_requested",
        "overtime_request",
        str(overtime_request.id),
        after={"booking_id": str(booking.id), "hours": hours},
    )
    db.commit()
    return overtime_request


def _open_request_for_sitter(db: Session, sitter_id: uuid.UUID, request_id: uuid.UUID) -> OvertimeRequest:
    overtime_request = db.scalar(select(OvertimeRequest).where(OvertimeRequest.id == request_id).with_for_update())
    if overtime_request is None:
        raise AppError(404, "not_found", "We couldn't find that request.")
    hers = db.scalar(
        select(Booking.id).where(Booking.id == overtime_request.booking_id, Booking.sitter_id == sitter_id)
    )
    if hers is None:
        raise AppError(404, "not_found", "We couldn't find that request.")
    if overtime_request.status != OvertimeRequestStatus.pending:
        raise AppError(409, "already_decided", "This request has already been answered.")
    return overtime_request


def decide(db: Session, sitter_id: uuid.UUID, request_id: uuid.UUID, accept: bool, now: datetime) -> OvertimeRequest:
    """She accepts or declines (6.8): nothing is charged either way, it's just between them."""
    overtime_request = _open_request_for_sitter(db, sitter_id, request_id)
    overtime_request.status = OvertimeRequestStatus.accepted if accept else OvertimeRequestStatus.declined
    overtime_request.decided_at = now
    audit.record(
        db,
        sitter_id,
        "overtime_decided",
        "overtime_request",
        str(overtime_request.id),
        after={"status": overtime_request.status.value},
    )
    db.commit()
    return overtime_request
