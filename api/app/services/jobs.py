"""Scheduled jobs (CLAUDE.md section 5). GitHub Actions calls /internal/jobs/<run> on a schedule; each run
is a list of tasks. Every task must be idempotent: running it twice, or late, changes nothing extra.

Later phases add their tasks here:
- daily: keeping the staging database active (strikes expire by their date, so they need no job)
- frequent (every 30 minutes, 6 am to midnight IST): cancelling unpaid bookings and paid ones that
  started with a child unverified, lapsing requests the sitter didn't answer in time, and alerting
  admins to payments unchecked near the start (phase 6), overdue check-out alerts (phase 8), and payouts
  due within 3 hours or overdue (phase 9), and escalating complaints past their target to the Grievance
  Officer (phase 10). Keep these quick.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from app.services import booking_mail, bookings, checkin, complaint_mail, complaints, payments, payouts
from app.services import email as email_service
from app.services.email import EmailClient
from app.settings import Settings


@dataclass(frozen=True)
class JobContext:
    settings: Settings
    mailer: EmailClient


Task = Callable[[Connection, JobContext], None]


def keep_database_active(conn: Connection, _ctx: JobContext) -> None:
    """A tiny query, so the free staging database isn't paused after a week without use."""
    conn.execute(text("SELECT 1"))


def cancel_unpaid_bookings(conn: Connection, _ctx: JobContext) -> None:
    """`pending_payment` bookings with no payment sent by 3 hours before the start (6.1). The run doesn't
    reach midnight to 6 am, so bookings are also checked when opened (`bookings.cancel_unpaid`)."""
    with Session(bind=conn) as db:
        bookings.cancel_unpaid(db, datetime.now(UTC))
        db.commit()  # the task's own transaction commits it (jobs router)


def cancel_unverified_bookings(conn: Connection, _ctx: JobContext) -> None:
    """Paid bookings that started with a child still unverified, cancelled and refunded (Reuben,
    2026-11-18). Also checked when the booking is opened (`bookings.cancel_unverified`)."""
    with Session(bind=conn) as db:
        bookings.cancel_unverified(db, datetime.now(UTC))
        db.commit()


def lapse_requests(conn: Connection, ctx: JobContext) -> None:
    """Requests the sitter didn't answer in time lapse, and the parents are told (Reuben, 2026-11-19).
    Also checked when the request or a list of them is opened (`bookings.lapse_requests`)."""
    with Session(bind=conn) as db:
        lapsed = bookings.lapse_requests(db, datetime.now(UTC))
        db.commit()
        for booking_id in lapsed:
            booking_mail.tell_parent_not_taken(db, ctx.mailer, ctx.settings, booking_id, lapsed=True)


def alert_unchecked_payments(conn: Connection, ctx: JobContext) -> None:
    """Booking payments still unchecked as their booking nears its start: the admins are emailed once
    for each (Reuben, 2026-11-19), so a payment rarely reaches the start unchecked."""
    recipients = ctx.settings.admin_alert_emails
    with Session(bind=conn) as db:
        found = payments.unchecked_near_start(db, datetime.now(UTC))
        if not found:
            return
        if not recipients:  # nobody to tell: left unmarked, so they're sent once someone is set
            return
        payments.mark_alerted(db, found)
        db.commit()
    web_url = ctx.settings.public_web_url or "http://localhost:5173"
    earliest = min(item.starts_at for item in found)
    for to in recipients:
        ctx.mailer.send(email_service.unchecked_payments_alert(to, len(found), earliest, web_url))


def alert_overdue_checkouts(conn: Connection, ctx: JobContext) -> None:
    """A booking still `in_progress` 30+ minutes past its end: the admins are emailed once for each
    (6.7), so they can call both people and close it by hand if it stays stuck."""
    recipients = ctx.settings.admin_alert_emails
    with Session(bind=conn) as db:
        found = checkin.overdue_not_alerted(db, datetime.now(UTC))
        if not found:
            return
        if not recipients:  # nobody to tell: left unmarked, so they're sent once someone is set
            return
        checkin.mark_overdue_alerted(db, found)
        db.commit()
        # Read these before the session closes below (its objects expire and can't be re-fetched after).
        times = [(booking.starts_at, booking.ends_at) for booking in found]
    web_url = ctx.settings.public_web_url or "http://localhost:5173"
    for starts_at, ends_at in times:
        for to in recipients:
            ctx.mailer.send(email_service.overdue_checkout_alert(to, starts_at, ends_at, web_url))


def alert_payouts(conn: Connection, ctx: JobContext) -> None:
    """Payouts with under 3 hours left, and payouts overdue: the admins are emailed once for each (6.10),
    one email per kind per run."""
    recipients = ctx.settings.admin_alert_emails
    if not recipients:  # nobody to tell: left unmarked, so they're sent once someone is set
        return
    now = datetime.now(UTC)
    with Session(bind=conn) as db:
        soon = payouts.due_soon_not_alerted(db, now)
        overdue = payouts.overdue_not_alerted(db, now)
        if not soon and not overdue:
            return
        earliest = min((item.due_by for item in soon), default=None)
        payouts.mark_alerted(db, payouts.DUE_SOON_ALERTED, soon)
        payouts.mark_alerted(db, payouts.OVERDUE_ALERTED, overdue)
        db.commit()
        counts = (len(soon), len(overdue))
    web_url = ctx.settings.public_web_url or "http://localhost:5173"
    for to in recipients:
        if counts[0] and earliest is not None:
            ctx.mailer.send(email_service.payouts_due_soon_alert(to, counts[0], earliest, web_url))
        if counts[1]:
            ctx.mailer.send(email_service.payouts_overdue_alert(to, counts[1], web_url))


def escalate_complaints(conn: Connection, ctx: JobContext) -> None:
    """Complaints still unresolved at their target (48 hours, or 15 days for a serious safety matter) go to
    the Grievance Officer (6.12); the people and the officer are emailed. Escalated ones aren't picked again."""
    with Session(bind=conn) as db:
        escalated = complaints.escalate_overdue(db, datetime.now(UTC))
        if not escalated:
            return
        db.commit()
        complaint_mail.tell_escalated(db, ctx.mailer, ctx.settings, escalated, overdue=True)


RUNS: dict[str, list[tuple[str, Task]]] = {
    "daily": [("keep_database_active", keep_database_active)],
    "frequent": [
        ("lapse_requests", lapse_requests),
        ("cancel_unpaid_bookings", cancel_unpaid_bookings),
        ("cancel_unverified_bookings", cancel_unverified_bookings),
        ("alert_unchecked_payments", alert_unchecked_payments),
        ("alert_overdue_checkouts", alert_overdue_checkouts),
        ("alert_payouts", alert_payouts),
        ("escalate_complaints", escalate_complaints),
    ],
}
