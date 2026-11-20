"""Reports during a booking (CLAUDE.md 6.5): the parent wasn't home, or the sitter didn't come.

- Parent not home: the sitter reports it, from the start until the end. Confirmed by an admin, the booking
  is `parent_absent`: the parent pays the whole booking and she's due ₹100 per booked hour.
- Only a man at home: the sitter may decline on the spot (decided 2026-11-12). Confirmed by an admin, the
  booking is `declined_man_at_home`: the parent pays the whole booking, no strike, ₹100 to her.
- Sitter no-show: the parent reports it, from 30 minutes after the start until the end. Confirmed by an
  admin, it's `sitter_no_show`: the parent is refunded, and she gets a strike and earns nothing.
- Child under 18 months: should never happen (bookings are blocked), but if it does the sitter reports it
  once an adult is with the child. Confirmed by an admin, it's `child_under_age`: the parent is charged for
  1 hour and refunded the rest; she's paid her level pay for that hour; no strike.
- Sitter feels unsafe: she may leave only once the child is with a parent. Confirmed by an admin, it's
  `sitter_left_unsafe`: the parent still pays the whole booking (kept from the Family Terms); she's paid
  for the time she worked (phase 9, once check-in exists); no strike.

Parent not home: she may leave only if no parent responds within 20 minutes of her report. A parent responds
with "I have arrived" in the app, or an admin marks that they answered the phone (Reuben, 2026-11-19); she
then waits for them. If a child is at home without an adult she must not report this and leave: she calls
for help instead (the Emergency button comes in phase 8). The show-up fee is paid with her other earnings
(phase 9, payouts); here the booking is marked `parent_absent`, which is what that will pay from.

The two reports below are also written through the Issues button's eventual place (phase 8); for now
they're the booking-page actions themselves, same as "only a man at home".
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Booking, BookingReport, BookingStatus, ReportKind, ReportStatus, StrikeReason
from app.services import audit, bookings, pricing, sitter_pay, strikes

PARENT_WAIT = timedelta(minutes=20)  # 6.5: she may leave if no parent responds within 20 minutes
NO_SHOW_AFTER = timedelta(minutes=30)  # Reuben, 2026-11-19: a no-show can be reported from 30 minutes in
SHOW_UP_FEE_PER_HOUR_PAISE = 10_000  # ₹100 per booked hour (6.5)
MAN_HOME_FEE_PAISE = 10_000  # a flat ₹100 when she declines because only a man is home (6.5)
UNDER_WAY = (BookingStatus.confirmed, BookingStatus.in_progress)


def can_leave_at(report: BookingReport) -> datetime | None:
    """When she may leave: 20 minutes after her report, unless a parent responded."""
    if report.kind != ReportKind.parent_absent or report.responded_at is not None:
        return None
    return report.reported_at + PARENT_WAIT


def show_up_fee_paise(booking: Booking) -> int:
    return SHOW_UP_FEE_PER_HOUR_PAISE * booking.units


def fee_paise(report: BookingReport, booking: Booking) -> int:
    """What Pacifyco pays her if the report is confirmed: the show-up fee, a flat ₹100, her level pay for
    one hour, or nothing (a no-show, or an unsafe exit -- she's paid for hours worked, worked out once
    check-in exists in phase 8)."""
    if report.kind == ReportKind.parent_absent:
        return show_up_fee_paise(booking)
    if report.kind == ReportKind.only_man_home:
        return MAN_HOME_FEE_PAISE
    if report.kind == ReportKind.child_under_age:
        return sitter_pay.booking_pay_paise(booking.plan, 1)
    return 0


def for_booking(db: Session, booking_id: uuid.UUID) -> BookingReport | None:
    """The booking's latest report, if any."""
    return db.scalar(
        select(BookingReport).where(BookingReport.booking_id == booking_id).order_by(BookingReport.reported_at.desc())
    )


def _new(db: Session, booking: Booking, kind: ReportKind, reporter_id: uuid.UUID, now: datetime) -> BookingReport:
    if db.scalar(select(BookingReport.id).where(BookingReport.booking_id == booking.id, BookingReport.kind == kind)):
        raise AppError(409, "already_reported", "This has already been reported. Pacifyco is looking at it.")
    report = BookingReport(booking_id=booking.id, kind=kind, reported_by=reporter_id, reported_at=now)
    db.add(report)
    db.flush()
    audit.record(
        db,
        reporter_id,
        "booking_reported",
        "booking_report",
        str(report.id),
        after={"booking_id": str(booking.id), "kind": kind.value},
    )
    db.commit()
    return report


def _booking(db: Session, booking_id: uuid.UUID, **owner) -> Booking:
    query = select(Booking).where(Booking.id == booking_id)
    for column, value in owner.items():
        query = query.where(getattr(Booking, column) == value)
    booking = db.scalar(query.with_for_update())
    if booking is None:
        raise AppError(404, "not_found", "We couldn't find that booking.")
    return booking


def parent_not_home(
    db: Session, sitter_id: uuid.UUID, booking_id: uuid.UUID, no_child_alone: bool, now: datetime
) -> BookingReport:
    """She's at the home and no parent is there. Only if no child is there without an adult (6.5)."""
    booking = _booking(db, booking_id, sitter_id=sitter_id)
    if booking.status not in UNDER_WAY:
        raise AppError(409, "cannot_report", "This booking can't be reported now.")
    if not booking.starts_at <= now < booking.ends_at:
        raise AppError(409, "not_booking_time", "You can report this once the booking has started.")
    if not no_child_alone:
        raise AppError(
            422,
            "child_alone",
            "If a child is at home without an adult, don't leave: stay with them, call the parent and Pacifyco, "
            "and call 112 if you need help.",
        )
    return _new(db, booking, ReportKind.parent_absent, sitter_id, now)


def only_man_home(db: Session, sitter_id: uuid.UUID, booking_id: uuid.UUID, now: datetime) -> BookingReport:
    """The only adult at home is a man: she may decline the booking on the spot (6.5; decided 2026-11-12).
    No strike; the parent pays the whole booking; Pacifyco pays her a flat ₹100 once an admin confirms."""
    booking = _booking(db, booking_id, sitter_id=sitter_id)
    if booking.status not in UNDER_WAY:
        raise AppError(409, "cannot_report", "This booking can't be reported now.")
    if not booking.starts_at <= now < booking.ends_at:
        raise AppError(409, "not_booking_time", "You can report this once the booking has started.")
    return _new(db, booking, ReportKind.only_man_home, sitter_id, now)


def child_under_age(
    db: Session, sitter_id: uuid.UUID, booking_id: uuid.UUID, adult_with_child: bool, now: datetime
) -> BookingReport:
    """A child on the booking is under 18 months, which should never happen (6.5): she isn't required to
    care for the child and may leave once an adult is with them."""
    booking = _booking(db, booking_id, sitter_id=sitter_id)
    if booking.status not in UNDER_WAY:
        raise AppError(409, "cannot_report", "This booking can't be reported now.")
    if not booking.starts_at <= now < booking.ends_at:
        raise AppError(409, "not_booking_time", "You can report this once the booking has started.")
    if not adult_with_child:
        raise AppError(
            422,
            "child_alone",
            "Don't leave until an adult is with the child. Call the parent and Pacifyco on +91 8848873841.",
        )
    return _new(db, booking, ReportKind.child_under_age, sitter_id, now)


def sitter_unsafe(
    db: Session, sitter_id: uuid.UUID, booking_id: uuid.UUID, child_with_parent: bool, now: datetime
) -> BookingReport:
    """She feels unsafe and needs to leave (6.5): only once the child is with a parent. The whole booking
    is still charged (kept from the Family Terms); she's paid for the time she worked (phase 9) and it's
    not a strike."""
    booking = _booking(db, booking_id, sitter_id=sitter_id)
    if booking.status not in UNDER_WAY:
        raise AppError(409, "cannot_report", "This booking can't be reported now.")
    if not booking.starts_at <= now < booking.ends_at:
        raise AppError(409, "not_booking_time", "You can report this once the booking has started.")
    if not child_with_parent:
        raise AppError(
            422,
            "child_alone",
            "Don't leave until the child is with a parent. Call Pacifyco on +91 8848873841, and 112 if you need help.",
        )
    return _new(db, booking, ReportKind.sitter_unsafe, sitter_id, now)


def sitter_no_show(db: Session, parent_id: uuid.UUID, booking_id: uuid.UUID, now: datetime) -> BookingReport:
    """The sitter didn't come: from 30 minutes after the start (Reuben, 2026-11-19)."""
    booking = _booking(db, booking_id, parent_id=parent_id)
    if booking.status not in UNDER_WAY:
        raise AppError(409, "cannot_report", "This booking can't be reported now.")
    if now < booking.starts_at + NO_SHOW_AFTER:
        raise AppError(409, "too_early", "You can report that your sitter didn't come from 30 minutes after the start.")
    if now >= booking.ends_at:
        raise AppError(409, "booking_over", "This booking has ended. Please contact Pacifyco.")
    return _new(db, booking, ReportKind.sitter_no_show, parent_id, now)


def _open_report(db: Session, report_id: uuid.UUID) -> BookingReport:
    report = db.scalar(select(BookingReport).where(BookingReport.id == report_id).with_for_update())
    if report is None:
        raise AppError(404, "not_found", "We couldn't find that report.")
    if report.status != ReportStatus.open:
        raise AppError(409, "already_decided", "This report has already been decided.")
    return report


def parent_responded(db: Session, actor_id: uuid.UUID, report_id: uuid.UUID, now: datetime) -> BookingReport:
    """A parent responded (in the app, or to an admin's call): the countdown stops and she waits."""
    report = _open_report(db, report_id)
    if report.kind != ReportKind.parent_absent:
        raise AppError(409, "not_parent_absent", "Only a 'parent not home' report can be answered.")
    if report.responded_at is not None:
        return report
    report.responded_at = now
    report.responded_by = actor_id
    audit.record(db, actor_id, "parent_responded", "booking_report", str(report.id), after={"responded": True})
    db.commit()
    return report


def parents_open_absence(db: Session, parent_id: uuid.UUID, booking_id: uuid.UUID) -> BookingReport:
    report = db.scalar(
        select(BookingReport)
        .join(Booking, Booking.id == BookingReport.booking_id)
        .where(
            Booking.id == booking_id,
            Booking.parent_id == parent_id,
            BookingReport.kind == ReportKind.parent_absent,
            BookingReport.status == ReportStatus.open,
        )
    )
    if report is None:
        raise AppError(404, "not_found", "There's nothing to answer for this booking.")
    return report


@dataclass(frozen=True)
class Decided:
    report: BookingReport
    booking: Booking
    strike: strikes.Outcome | None = None


def decide(
    db: Session, admin_id: uuid.UUID, report_id: uuid.UUID, confirm: bool, note: str | None, now: datetime
) -> Decided:
    """An admin confirms or dismisses a report. Confirming a parent-not-home report needs the 20 minutes
    to have passed with no parent responding."""
    report = _open_report(db, report_id)
    booking = db.scalar(select(Booking).where(Booking.id == report.booking_id).with_for_update())
    assert booking is not None
    outcome = None
    if confirm:
        if report.kind == ReportKind.parent_absent:
            leave = can_leave_at(report)
            if leave is None:
                raise AppError(409, "parent_responded", "A parent responded, so this can't be confirmed.")
            if now < leave:
                raise AppError(409, "still_waiting", "The 20 minutes for a parent to respond haven't passed yet.")
            status = BookingStatus.parent_absent
        elif report.kind == ReportKind.only_man_home:
            status = BookingStatus.declined_man_at_home  # charged in full, no strike (6.5)
        elif report.kind == ReportKind.child_under_age:
            status = BookingStatus.child_under_age
        elif report.kind == ReportKind.sitter_unsafe:
            status = BookingStatus.sitter_left_unsafe  # charged in full, no strike (6.5)
        else:
            status = BookingStatus.sitter_no_show
        if booking.status not in UNDER_WAY:
            raise AppError(409, "cannot_confirm", "This booking has already been closed.")
        audit.record(
            db,
            admin_id,
            "booking_closed",
            "booking",
            str(booking.id),
            before={"status": booking.status.value},
            after={"status": status.value, "report_id": str(report.id)},
        )
        booking.status = status
        db.flush()
        if status == BookingStatus.sitter_no_show:
            # The parent's money comes back; she earns nothing and gets a strike (6.5, 6.6).
            bookings.refund_booking(db, admin_id, booking.id)
            outcome = strikes.give(db, admin_id, booking.sitter_id, StrikeReason.no_show, now, booking_id=booking.id)
        elif status == BookingStatus.child_under_age:
            # 1 hour charged, the rest refunded (6.5).
            keep = pricing.hourly_price_paise(booking.plan, booking.children_count)
            bookings.refund_under_age(db, admin_id, booking.id, keep)
    report.status = ReportStatus.confirmed if confirm else ReportStatus.dismissed
    report.decided_by = admin_id
    report.decided_at = now
    report.decision_note = note
    audit.record(
        db,
        admin_id,
        "report_confirmed" if confirm else "report_dismissed",
        "booking_report",
        str(report.id),
        after={"status": report.status.value, "note": note},
    )
    db.commit()
    return Decided(report, booking, outcome)


def open_reports(db: Session) -> list[BookingReport]:
    """Reports waiting for an admin, oldest first."""
    return list(
        db.scalars(
            select(BookingReport).where(BookingReport.status == ReportStatus.open).order_by(BookingReport.reported_at)
        )
    )
