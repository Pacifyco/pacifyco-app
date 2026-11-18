"""Scheduled jobs (CLAUDE.md section 5). GitHub Actions calls /internal/jobs/<run> on a schedule; each run
is a list of tasks. Every task must be idempotent: running it twice, or late, changes nothing extra.

Later phases add their tasks here:
- daily: pack expiry and carry-forward (phase 6), strike expiry (phase 7)
- frequent (every 30 minutes, 6 am to midnight IST): cancelling unpaid bookings (phase 6), overdue
  check-out alerts (phase 8), payouts-due alerts (phase 9). Keep these quick.
"""

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from app.services import bookings

Task = Callable[[Connection], None]


def keep_database_active(conn: Connection) -> None:
    """A tiny query, so the free staging database isn't paused after a week without use."""
    conn.execute(text("SELECT 1"))


def cancel_unpaid_bookings(conn: Connection) -> None:
    """`pending_payment` bookings with no payment sent by 3 hours before the start (6.1). The run doesn't
    reach midnight to 6 am, so bookings are also checked when opened (`bookings.cancel_unpaid`)."""
    with Session(bind=conn) as db:
        bookings.cancel_unpaid(db, datetime.now(UTC))
        db.commit()  # the task's own transaction commits it (jobs router)


RUNS: dict[str, list[tuple[str, Task]]] = {
    "daily": [("keep_database_active", keep_database_active)],
    "frequent": [("cancel_unpaid_bookings", cancel_unpaid_bookings)],
}
