"""The admin dashboard (phase 10): counts of what's waiting, each linking to its queue.

Counts and amounts only, never names or bank details, so the home page can refresh it on a timer.
"Today's payouts" (Reuben, 2026-11-22): what's due now (count, total, how many overdue) and what's been
paid today, India time. Also open reports, overdue check-outs, open issues and low ratings (same day).
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import EarningStatus, IncidentStatus, Payout, SitterEarning
from app.services import checkin, incidents, payments, reports, reviews, verification
from app.services.availability import INDIA, today_in_india


@dataclass
class Counts:
    incidents_open: int  # not yet acknowledged
    incidents_unresolved: int  # open or acknowledged
    sitters_to_review: int
    families_to_review: int
    payments_to_check: int  # booking payments, and charges with a reference sent
    refunds_to_pay: int
    payouts_due: int  # released, unpaid earnings
    payouts_due_paise: int
    payouts_overdue: int
    paid_today: int  # transfers marked paid today, India time
    paid_today_paise: int
    reports_open: int
    overdue_checkouts: int  # bookings needing a call: overdue check-out or codes locked
    issues_open: int
    low_ratings: int  # rating flags not yet closed


def _start_of_today(now: datetime) -> datetime:
    return datetime.combine(today_in_india(now), time(), INDIA)


def counts(db: Session, now: datetime) -> Counts:
    unresolved = incidents.open_incidents(db)
    to_check, refunds = payments.waiting_for_admins(db)
    released = SitterEarning.status == EarningStatus.released
    due_count, due_paise = db.execute(
        select(func.count(SitterEarning.id), func.coalesce(func.sum(SitterEarning.amount_paise), 0)).where(released)
    ).one()
    overdue = db.scalar(select(func.count(SitterEarning.id)).where(released, SitterEarning.due_by < now)) or 0
    today = _start_of_today(now)
    paid_count, paid_paise = db.execute(
        select(func.count(Payout.id), func.coalesce(func.sum(Payout.amount_paise), 0)).where(
            Payout.paid_at >= today, Payout.paid_at < today + timedelta(days=1)
        )
    ).one()
    return Counts(
        incidents_open=sum(1 for item in unresolved if item.status == IncidentStatus.open),
        incidents_unresolved=len(unresolved),
        sitters_to_review=len(verification.sitters_to_review(db)),
        families_to_review=len(verification.families_to_review(db)),
        payments_to_check=len(to_check),
        refunds_to_pay=len(refunds),
        payouts_due=due_count,
        payouts_due_paise=int(due_paise),
        payouts_overdue=overdue,
        paid_today=paid_count,
        paid_today_paise=int(paid_paise),
        reports_open=len(reports.open_reports(db)),
        overdue_checkouts=len(checkin.needing_attention(db, now)),
        issues_open=len(incidents.open_issues(db)),
        low_ratings=len(reviews.open_flags(db)),
    )
