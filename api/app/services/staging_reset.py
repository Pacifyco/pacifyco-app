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
    AccountActionRow,
    AuditLog,
    Booking,
    BookingReport,
    Child,
    Complaint,
    ComplaintMessage,
    Consent,
    Document,
    DocumentAccessLog,
    Incident,
    LegalAcceptance,
    Message,
    OvertimeCharge,
    OvertimeRequest,
    Payment,
    Payout,
    Profile,
    PsychAttempt,
    RatingFlag,
    Reference,
    Review,
    Role,
    SitterEarning,
    Strike,
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
    booking_ids = db.scalars(
        select(Booking.id).where(or_(Booking.parent_id.in_(ids), Booking.sitter_id.in_(ids)))
    ).all()
    payment_ids = db.scalars(select(Payment.id).where(Payment.booking_id.in_(booking_ids))).all()
    strike_ids = db.scalars(
        select(Strike.id).where(or_(Strike.booking_id.in_(booking_ids), Strike.sitter_id.in_(ids)))
    ).all()
    report_ids = db.scalars(select(BookingReport.id).where(BookingReport.booking_id.in_(booking_ids))).all()
    overtime_request_ids = db.scalars(
        select(OvertimeRequest.id).where(OvertimeRequest.booking_id.in_(booking_ids))
    ).all()
    overtime_charge_ids = db.scalars(select(OvertimeCharge.id).where(OvertimeCharge.booking_id.in_(booking_ids))).all()
    incident_ids = db.scalars(select(Incident.id).where(Incident.booking_id.in_(booking_ids))).all()
    earning_ids = db.scalars(
        select(SitterEarning.id).where(or_(SitterEarning.booking_id.in_(booking_ids), SitterEarning.sitter_id.in_(ids)))
    ).all()
    payout_ids = db.scalars(select(Payout.id).where(Payout.sitter_id.in_(ids))).all()
    review_ids = db.scalars(
        select(Review.id).where(
            or_(Review.booking_id.in_(booking_ids), Review.author_id.in_(ids), Review.subject_id.in_(ids))
        )
    ).all()
    flag_ids = db.scalars(select(RatingFlag.id).where(RatingFlag.sitter_id.in_(ids))).all()
    complaint_ids = db.scalars(
        select(Complaint.id).where(or_(Complaint.booking_id.in_(booking_ids), Complaint.raised_by.in_(ids)))
    ).all()
    # Audit rows they made, and rows about them or their records (entity ids are stored as text).
    records = [
        *ids,
        *child_ids,
        *document_ids,
        *reference_ids,
        *attempt_ids,
        *booking_ids,
        *payment_ids,
        *strike_ids,
        *report_ids,
        *overtime_request_ids,
        *overtime_charge_ids,
        *incident_ids,
        *earning_ids,
        *payout_ids,
        *review_ids,
        *flag_ids,
        *complaint_ids,
    ]
    about = [str(item) for item in records]

    # Payments, then bookings: they hold their parent, sitter and children (RESTRICT); a booking's
    # children and home info rows go with it.
    db.execute(delete(Payment).where(Payment.id.in_(payment_ids)))
    db.execute(delete(SitterEarning).where(SitterEarning.id.in_(earning_ids)))
    db.execute(delete(Payout).where(Payout.id.in_(payout_ids)))
    db.execute(delete(Strike).where(Strike.id.in_(strike_ids)))
    db.execute(delete(BookingReport).where(BookingReport.id.in_(report_ids)))
    db.execute(delete(OvertimeRequest).where(OvertimeRequest.id.in_(overtime_request_ids)))
    db.execute(delete(OvertimeCharge).where(OvertimeCharge.id.in_(overtime_charge_ids)))
    db.execute(delete(Incident).where(Incident.id.in_(incident_ids)))
    # Documents before complaints (a complaint's attachments hold it), its messages too.
    db.execute(delete(DocumentAccessLog).where(DocumentAccessLog.document_id.in_(document_ids)))
    db.execute(delete(Document).where(Document.id.in_(document_ids)))
    db.execute(delete(ComplaintMessage).where(ComplaintMessage.complaint_id.in_(complaint_ids)))
    db.execute(delete(Complaint).where(Complaint.id.in_(complaint_ids)))
    db.execute(delete(Review).where(Review.id.in_(review_ids)))
    db.execute(delete(RatingFlag).where(RatingFlag.id.in_(flag_ids)))
    db.execute(delete(AccountActionRow).where(AccountActionRow.profile_id.in_(ids)))
    db.execute(delete(Message).where(or_(Message.parent_id.in_(ids), Message.sitter_id.in_(ids))))
    db.execute(delete(Booking).where(Booking.id.in_(booking_ids)))
    db.execute(delete(Consent).where(Consent.parent_id.in_(ids)))
    db.execute(delete(LegalAcceptance).where(LegalAcceptance.profile_id.in_(ids)))
    db.execute(delete(AuditLog).where(or_(AuditLog.actor_id.in_(ids), AuditLog.entity_id.in_(about))))
    db.execute(delete(Profile).where(Profile.id.in_(ids)))
    db.commit()
