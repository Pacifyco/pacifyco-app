"""Complaints and grievances (CLAUDE.md 6.12; phase 10, Reuben 2026-11-23).

- **Raising one:** a parent or sitter raises a complaint from Help (about a booking, a payment, the other
  side, a review or something else), with a description and up to 3 attachments; the Issues button on a
  booking raises one too. Raised more than 24 hours after it happened (the booking's end, or the date they
  give), it's accepted but flagged late.
- **Targets:** a first reply within 24 hours and resolved within 48 hours; an admin can mark it a serious
  safety matter, which gives it 15 days (with updates). Admins and the person write to each other on it; the
  first message from Pacifyco is the first reply.
- **Escalation:** still unresolved at its target, the frequent job escalates it to the Grievance Officer; the
  person can also escalate one that's been resolved if they disagree. The officer acknowledges it (target 24
  hours) and gives a written decision with reasons (target 15 days), which closes it.
- **The Grievance Officer** is the admin whose email is `GRIEVANCE_OFFICER_EMAIL`; while that's empty, every
  admin acts as the officer. Only the officer handles an escalated complaint.
- **Appeals:** someone whose account was suspended or removed can appeal from the app within 15 days of the
  decision, once per decision. It's reviewed within 7 working days (Monday to Friday, not public holidays,
  which admins add). The admin who made the decision can't handle the appeal; any admin can when the rules
  made it (a 5th strike, a theft or abuse report). Upheld, the admin reinstates the account then, or leaves
  it to reinstate by hand later.

Every step is audit logged. Messages are append-only.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import BLOCKED_STATUSES
from app.errors import AppError
from app.models import (
    AccountAction,
    AccountActionRow,
    AppealOutcome,
    Booking,
    Complaint,
    ComplaintMessage,
    ComplaintStatus,
    ComplaintType,
    Document,
    DocumentStatus,
    Profile,
    PublicHoliday,
)
from app.services import account_status, audit
from app.services.availability import INDIA
from app.settings import Settings

REPLY_WITHIN = timedelta(hours=24)
RESOLVE_WITHIN = timedelta(hours=48)
SERIOUS_WITHIN = timedelta(days=15)
LATE_AFTER = timedelta(hours=24)
APPEAL_WINDOW = timedelta(days=15)
APPEAL_WORKING_DAYS = 7
OFFICER_ACKNOWLEDGE_WITHIN = timedelta(hours=24)
OFFICER_DECIDE_WITHIN = timedelta(days=15)
TEXT_MAX = 2000
ATTACHMENTS_MAX = 3

RAISABLE = (
    ComplaintType.booking,
    ComplaintType.payment,
    ComplaintType.family,
    ComplaintType.sitter,
    ComplaintType.review,
    ComplaintType.other,
)
ACTIVE = (ComplaintStatus.open, ComplaintStatus.replied)
VIEWS = ("open", "appeals", "escalated", "done")


# ---------- helpers ----------


def is_officer(settings: Settings, admin: Profile) -> bool:
    officer = settings.grievance_officer_email.strip().lower()
    return not officer or admin.email.strip().lower() == officer


def officer_emails(settings: Settings) -> list[str]:
    officer = settings.grievance_officer_email.strip()
    return [officer] if officer else list(settings.admin_alert_emails)


def _text(value: str | None, what: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise AppError(422, "text_needed", f"Please write {what}.")
    if len(cleaned) > TEXT_MAX:
        raise AppError(422, "text_too_long", f"Please keep it under {TEXT_MAX:,} characters.")
    return cleaned


def working_days_after(db: Session, start: datetime, days: int) -> datetime:
    """The end (midnight, India time) of the `days`th working day after `start`'s India date: Monday to
    Friday, and not a public holiday."""
    day = start.astimezone(INDIA).date()
    holidays = set(
        db.scalars(
            select(PublicHoliday.day).where(PublicHoliday.day > day, PublicHoliday.day <= day + timedelta(days=60))
        )
    )
    counted = 0
    while counted < days:
        day += timedelta(days=1)
        if day.weekday() < 5 and day not in holidays:
            counted += 1
    return datetime.combine(day + timedelta(days=1), time(), INDIA)


def _late(booking: Booking | None, happened_on: date | None, now: datetime) -> bool:
    if booking is not None:
        return now - (booking.checked_out_at or booking.ends_at) > LATE_AFTER
    if happened_on is not None:
        return now.astimezone(INDIA).date() - happened_on > timedelta(days=1)
    return False


def new_complaint(raised_by: uuid.UUID, kind: ComplaintType, description: str, now: datetime, **fields) -> Complaint:
    """A complaint with its 24- and 48-hour targets (also used by the Issues button)."""
    return Complaint(
        raised_by=raised_by,
        type=kind,
        description=description,
        created_at=now,
        reply_by=now + REPLY_WITHIN,
        resolve_by=now + RESOLVE_WITHIN,
        **fields,
    )


def _complaint(db: Session, complaint_id: uuid.UUID) -> Complaint:
    complaint = db.scalar(select(Complaint).where(Complaint.id == complaint_id).with_for_update())
    if complaint is None:
        raise AppError(404, "not_found", "We couldn't find that complaint.")
    return complaint


def decision_of(db: Session, complaint: Complaint) -> AccountActionRow | None:
    """The suspension or removal an appeal is against."""
    return db.get(AccountActionRow, complaint.account_action_id) if complaint.account_action_id else None


def messages(db: Session, complaint_id: uuid.UUID) -> list[ComplaintMessage]:
    return list(
        db.scalars(
            select(ComplaintMessage)
            .where(ComplaintMessage.complaint_id == complaint_id)
            .order_by(ComplaintMessage.created_at, ComplaintMessage.id)
        )
    )


def attachments(db: Session, complaint_id: uuid.UUID) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.complaint_id == complaint_id, Document.status == DocumentStatus.uploaded)
            .order_by(Document.created_at)
        )
    )


def check_attachment(db: Session, owner_id: uuid.UUID, complaint_id: uuid.UUID) -> None:
    """Before an upload: their own complaint, still open, under 3 attachments."""
    complaint = db.get(Complaint, complaint_id)
    if complaint is None or complaint.raised_by != owner_id:
        raise AppError(404, "not_found", "We couldn't find that complaint.")
    if complaint.status == ComplaintStatus.closed:
        raise AppError(409, "complaint_closed", "This complaint is closed.")
    count = db.scalar(
        select(func.count())
        .select_from(Document)
        .where(Document.complaint_id == complaint_id, Document.status != DocumentStatus.invalid)
    )
    if count >= ATTACHMENTS_MAX:
        raise AppError(409, "too_many_attachments", f"A complaint can have up to {ATTACHMENTS_MAX} files.")


# ---------- the person ----------


def raise_complaint(
    db: Session,
    person: Profile,
    kind: ComplaintType,
    description: str,
    booking_id: uuid.UUID | None,
    happened_on: date | None,
    now: datetime,
) -> Complaint:
    if kind not in RAISABLE:
        raise AppError(422, "invalid_type", "Choose what the complaint is about.")
    booking = None
    if booking_id is not None:
        booking = db.get(Booking, booking_id)
        if booking is None or person.id not in (booking.parent_id, booking.sitter_id):
            raise AppError(404, "not_found", "We couldn't find that booking.")
        happened_on = None
    elif kind == ComplaintType.booking:
        raise AppError(422, "booking_needed", "Choose the booking it's about.")
    if happened_on is not None and happened_on > now.astimezone(INDIA).date():
        raise AppError(422, "date_in_future", "That date hasn't come yet.")
    complaint = new_complaint(
        person.id,
        kind,
        _text(description, "what happened"),
        now,
        booking_id=booking_id,
        happened_on=happened_on,
        late=_late(booking, happened_on, now),
    )
    db.add(complaint)
    db.flush()
    audit.record(
        db,
        person.id,
        "complaint_raised",
        "complaint",
        str(complaint.id),
        after={"type": kind.value, "booking_id": str(booking_id) if booking_id else None, "late": complaint.late},
    )
    db.commit()
    return complaint


def mine(db: Session, person_id: uuid.UUID) -> list[Complaint]:
    return list(
        db.scalars(select(Complaint).where(Complaint.raised_by == person_id).order_by(Complaint.created_at.desc()))
    )


def persons(db: Session, person: Profile, complaint_id: uuid.UUID) -> Complaint:
    """Their own complaint. A suspended or removed account sees only its appeal."""
    complaint = db.get(Complaint, complaint_id)
    if complaint is None or complaint.raised_by != person.id:
        raise AppError(404, "not_found", "We couldn't find that complaint.")
    if person.status in BLOCKED_STATUSES and complaint.type != ComplaintType.suspension:
        raise AppError(403, "account_blocked", "Your account is on hold. Please contact Pacifyco.")
    return complaint


def person_writes(db: Session, person: Profile, complaint_id: uuid.UUID, body: str, now: datetime) -> Complaint:
    complaint = persons(db, person, complaint_id)
    if complaint.status == ComplaintStatus.closed:
        raise AppError(409, "complaint_closed", "This complaint is closed.")
    db.add(
        ComplaintMessage(complaint_id=complaint.id, author_id=person.id, body=_text(body, "a message"), created_at=now)
    )
    db.commit()
    return complaint


def person_escalates(db: Session, person: Profile, complaint_id: uuid.UUID, why: str, now: datetime) -> Complaint:
    """They disagree with how it was resolved: to the Grievance Officer."""
    persons(db, person, complaint_id)
    complaint = _complaint(db, complaint_id)
    if complaint.status != ComplaintStatus.resolved:
        raise AppError(409, "cannot_escalate", "You can send it to the Grievance Officer once it's been resolved.")
    _escalate(db, complaint, person.id, _text(why, "why you disagree"), now)
    db.commit()
    return complaint


def _escalate(db: Session, complaint: Complaint, by: uuid.UUID | None, why: str | None, now: datetime) -> None:
    audit.record(
        db,
        by,
        "complaint_escalated",
        "complaint",
        str(complaint.id),
        before={"status": complaint.status.value},
        after={"status": ComplaintStatus.escalated.value, "why": "disagreed" if by else "overdue"},
    )
    complaint.status = ComplaintStatus.escalated
    complaint.escalated_at = now
    complaint.escalated_by = by
    complaint.escalation_note = why


# ---------- appeals ----------


@dataclass
class AppealState:
    decision: AccountActionRow | None  # the latest suspension or removal, while the account is blocked
    appeal_by: datetime | None
    appeal: Complaint | None


def appeal_state(db: Session, person: Profile) -> AppealState:
    if person.status not in BLOCKED_STATUSES:
        return AppealState(None, None, None)
    decision = db.scalar(
        select(AccountActionRow)
        .where(
            AccountActionRow.profile_id == person.id,
            AccountActionRow.action.in_((AccountAction.suspended, AccountAction.removed)),
        )
        .order_by(AccountActionRow.created_at.desc())
        .limit(1)
    )
    if decision is None:
        return AppealState(None, None, None)
    appeal = db.scalar(select(Complaint).where(Complaint.account_action_id == decision.id))
    return AppealState(decision, decision.created_at + APPEAL_WINDOW, appeal)


def appeal(db: Session, person: Profile, description: str, now: datetime) -> Complaint:
    state = appeal_state(db, person)
    if state.decision is None:
        raise AppError(409, "nothing_to_appeal", "There's no decision on your account to appeal.")
    if state.appeal is not None:
        raise AppError(409, "already_appealed", "You've already appealed this decision.")
    if state.appeal_by is not None and now > state.appeal_by:
        raise AppError(409, "appeal_too_late", "Appeals can be made within 15 days of the decision.")
    complaint = new_complaint(
        person.id,
        ComplaintType.suspension,
        _text(description, "why you're appealing"),
        now,
        account_action_id=state.decision.id,
    )
    complaint.resolve_by = working_days_after(db, now, APPEAL_WORKING_DAYS)
    db.add(complaint)
    db.flush()
    audit.record(
        db,
        person.id,
        "appeal_raised",
        "complaint",
        str(complaint.id),
        after={"account_action_id": str(state.decision.id), "decision": state.decision.action.value},
    )
    db.commit()
    return complaint


# ---------- admins ----------


def can_handle(db: Session, settings: Settings, admin: Profile, complaint: Complaint) -> str | None:
    """Why this admin can't act on it, or None if they can."""
    decision = decision_of(db, complaint)
    if decision is not None and decision.admin_id == admin.id:
        return "You made the decision this appeal is against, so another admin must handle it."
    if complaint.status == ComplaintStatus.escalated and not is_officer(settings, admin):
        return "This is with the Grievance Officer."
    if complaint.status == ComplaintStatus.closed:
        return "This complaint is closed."
    return None


def _handled_by(db: Session, settings: Settings, admin: Profile, complaint_id: uuid.UUID) -> Complaint:
    complaint = _complaint(db, complaint_id)
    why = can_handle(db, settings, admin, complaint)
    if why is not None:
        raise AppError(403, "cannot_handle", why)
    return complaint


def queue(db: Session, view: str) -> list[Complaint]:
    query = select(Complaint)
    if view == "open":
        query = query.where(Complaint.status.in_(ACTIVE), Complaint.type != ComplaintType.suspension)
        query = query.order_by(Complaint.resolve_by, Complaint.created_at)
    elif view == "appeals":
        query = query.where(Complaint.status.in_(ACTIVE), Complaint.type == ComplaintType.suspension)
        query = query.order_by(Complaint.resolve_by, Complaint.created_at)
    elif view == "escalated":
        query = query.where(Complaint.status == ComplaintStatus.escalated).order_by(Complaint.escalated_at)
    else:  # done: resolved by an admin or decided by the officer
        query = query.where(Complaint.status.in_((ComplaintStatus.resolved, ComplaintStatus.closed)))
        query = query.order_by(Complaint.created_at.desc()).limit(100)
    return list(db.scalars(query))


def admin_writes(
    db: Session, settings: Settings, admin: Profile, complaint_id: uuid.UUID, body: str, now: datetime
) -> Complaint:
    """A message to the person; the first one is Pacifyco's first reply."""
    complaint = _handled_by(db, settings, admin, complaint_id)
    db.add(
        ComplaintMessage(complaint_id=complaint.id, author_id=admin.id, body=_text(body, "a message"), created_at=now)
    )
    if complaint.first_reply_at is None:
        complaint.first_reply_at = now
        audit.record(db, admin.id, "complaint_replied", "complaint", str(complaint.id), after={"first_reply": True})
    if complaint.status == ComplaintStatus.open:
        complaint.status = ComplaintStatus.replied
    db.commit()
    return complaint


def mark_serious(
    db: Session, settings: Settings, admin: Profile, complaint_id: uuid.UUID, serious: bool, now: datetime
) -> Complaint:
    """A serious safety matter: 15 days to resolve, with updates, instead of 48 hours."""
    complaint = _handled_by(db, settings, admin, complaint_id)
    if complaint.status not in ACTIVE or complaint.type == ComplaintType.suspension:
        raise AppError(409, "cannot_mark", "Only an open complaint can be marked a serious safety matter.")
    if complaint.serious != serious:
        audit.record(
            db,
            admin.id,
            "complaint_marked_serious" if serious else "complaint_unmarked_serious",
            "complaint",
            str(complaint.id),
            before={"serious": complaint.serious},
            after={"serious": serious},
        )
        complaint.serious = serious
        complaint.resolve_by = complaint.created_at + (SERIOUS_WITHIN if serious else RESOLVE_WITHIN)
    db.commit()
    return complaint


def resolve(
    db: Session, settings: Settings, admin: Profile, complaint_id: uuid.UUID, resolution: str, now: datetime
) -> Complaint:
    complaint = _handled_by(db, settings, admin, complaint_id)
    if complaint.type == ComplaintType.suspension:
        raise AppError(409, "is_an_appeal", "Decide the appeal instead.")
    if complaint.status not in ACTIVE:
        raise AppError(409, "not_open", "This complaint isn't open.")
    _decided(db, admin, complaint, _text(resolution, "what was done"), now)
    db.commit()
    return complaint


def _decided(db: Session, admin: Profile, complaint: Complaint, resolution: str, now: datetime, **after) -> None:
    audit.record(
        db,
        admin.id,
        "appeal_decided" if complaint.type == ComplaintType.suspension else "complaint_resolved",
        "complaint",
        str(complaint.id),
        before={"status": complaint.status.value},
        after={"status": ComplaintStatus.resolved.value, "resolution": resolution, **after},
    )
    complaint.status = ComplaintStatus.resolved
    complaint.resolution = resolution
    complaint.resolved_at = now
    complaint.decided_by = admin.id
    if complaint.first_reply_at is None:
        complaint.first_reply_at = now


def decide_appeal(
    db: Session,
    settings: Settings,
    admin: Profile,
    complaint_id: uuid.UUID,
    outcome: AppealOutcome,
    note: str,
    reinstate: bool,
    now: datetime,
) -> Complaint:
    """Upheld: the account is reinstated now, or left for an admin to reinstate by hand. Rejected: it stands."""
    complaint = _handled_by(db, settings, admin, complaint_id)
    if complaint.type != ComplaintType.suspension:
        raise AppError(409, "not_an_appeal", "This isn't an appeal.")
    if complaint.status not in ACTIVE:
        raise AppError(409, "not_open", "This appeal has already been decided.")
    if reinstate and outcome != AppealOutcome.upheld:
        raise AppError(422, "reinstate_needs_upheld", "Only an upheld appeal can reinstate the account.")
    note = _text(note, "the reasons for the decision")
    complaint.appeal_outcome = outcome
    _decided(db, admin, complaint, note, now, outcome=outcome.value, reinstated=reinstate)
    if reinstate:
        account_status.reinstate(db, admin.id, complaint.raised_by, f"Appeal upheld: {note}", now)  # commits
    else:
        db.commit()
    return complaint


def officer_acknowledges(
    db: Session, settings: Settings, admin: Profile, complaint_id: uuid.UUID, now: datetime
) -> Complaint:
    complaint = _handled_by(db, settings, admin, complaint_id)
    if complaint.status != ComplaintStatus.escalated:
        raise AppError(409, "not_escalated", "This complaint isn't with the Grievance Officer.")
    if complaint.officer_acknowledged_at is None:
        complaint.officer_acknowledged_at = now
        complaint.officer_id = admin.id
        audit.record(db, admin.id, "complaint_acknowledged_by_officer", "complaint", str(complaint.id))
    db.commit()
    return complaint


def officer_decides(
    db: Session, settings: Settings, admin: Profile, complaint_id: uuid.UUID, decision: str, now: datetime
) -> Complaint:
    """The Grievance Officer's written decision, with reasons. Final: the complaint is closed."""
    complaint = _handled_by(db, settings, admin, complaint_id)
    if complaint.status != ComplaintStatus.escalated:
        raise AppError(409, "not_escalated", "This complaint isn't with the Grievance Officer.")
    decision = _text(decision, "the decision and its reasons")
    audit.record(
        db,
        admin.id,
        "complaint_decided_by_officer",
        "complaint",
        str(complaint.id),
        before={"status": complaint.status.value},
        after={"status": ComplaintStatus.closed.value, "decision": decision},
    )
    complaint.officer_acknowledged_at = complaint.officer_acknowledged_at or now
    complaint.officer_id = admin.id
    complaint.officer_decision = decision
    complaint.officer_decided_at = now
    complaint.status = ComplaintStatus.closed
    db.commit()
    return complaint


def escalate_overdue(db: Session, now: datetime) -> list[Complaint]:
    """Complaints still open at their target go to the Grievance Officer (the frequent job). Appeals don't:
    they're shown overdue instead. The caller commits."""
    overdue = list(
        db.scalars(
            select(Complaint)
            .where(
                Complaint.status.in_(ACTIVE),
                Complaint.type != ComplaintType.suspension,
                Complaint.resolve_by <= now,
            )
            .with_for_update(skip_locked=True)
        )
    )
    for complaint in overdue:
        _escalate(db, complaint, None, None, now)
    return overdue


def waiting(db: Session, now: datetime) -> tuple[int, int]:
    """Complaints and appeals not yet resolved (escalated ones too), and how many are past a target."""
    found = list(db.scalars(select(Complaint).where(Complaint.status.in_((*ACTIVE, ComplaintStatus.escalated)))))
    return len(found), sum(1 for complaint in found if overdue(complaint, now))


def overdue(complaint: Complaint, now: datetime) -> bool:
    """Past its target: the first reply, resolving it, or the officer's acknowledgement or decision."""
    if complaint.status in ACTIVE:
        return complaint.resolve_by < now or (complaint.first_reply_at is None and complaint.reply_by < now)
    if complaint.status == ComplaintStatus.escalated and complaint.escalated_at is not None:
        if complaint.officer_acknowledged_at is None and complaint.escalated_at + OFFICER_ACKNOWLEDGE_WITHIN < now:
            return True
        return complaint.escalated_at + OFFICER_DECIDE_WITHIN < now
    return False


# ---------- public holidays ----------


def holidays(db: Session, since: date) -> list[PublicHoliday]:
    return list(db.scalars(select(PublicHoliday).where(PublicHoliday.day >= since).order_by(PublicHoliday.day)))


def add_holiday(db: Session, admin_id: uuid.UUID, day: date, name: str) -> PublicHoliday:
    name = (name or "").strip()
    if not name or len(name) > 100:
        raise AppError(422, "name_needed", "Give the holiday a name (up to 100 characters).")
    if db.get(PublicHoliday, day) is not None:
        raise AppError(409, "already_a_holiday", "That day is already a public holiday.")
    holiday = PublicHoliday(day=day, name=name)
    db.add(holiday)
    audit.record(db, admin_id, "holiday_added", "public_holiday", day.isoformat(), after={"name": name})
    db.commit()
    return holiday


def remove_holiday(db: Session, admin_id: uuid.UUID, day: date) -> None:
    holiday = db.get(PublicHoliday, day)
    if holiday is None:
        raise AppError(404, "not_found", "That day isn't a public holiday.")
    audit.record(db, admin_id, "holiday_removed", "public_holiday", day.isoformat(), before={"name": holiday.name})
    db.delete(holiday)
    db.commit()
