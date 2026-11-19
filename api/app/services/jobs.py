"""Scheduled jobs (CLAUDE.md section 5). GitHub Actions calls /internal/jobs/<run> on a schedule; each run
is a list of tasks. Every task must be idempotent: running it twice, or late, changes nothing extra.

Later phases add their tasks here:
- daily: keeping the staging database active (strikes expire by their date, so they need no job)
- frequent (every 30 minutes, 6 am to midnight IST): cancelling unpaid bookings and paid ones that
  started with a child unverified, lapsing requests the sitter didn't answer in time, and alerting
  admins to payments unchecked near the start (phase 6), overdue check-out alerts (phase 8),
  payouts-due alerts (phase 9). Keep these quick.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from app.services import booking_mail, bookings, payments
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


RUNS: dict[str, list[tuple[str, Task]]] = {
    "daily": [("keep_database_active", keep_database_active)],
    "frequent": [
        ("lapse_requests", lapse_requests),
        ("cancel_unpaid_bookings", cancel_unpaid_bookings),
        ("cancel_unverified_bookings", cancel_unverified_bookings),
        ("alert_unchecked_payments", alert_unchecked_payments),
    ],
}
