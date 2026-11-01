"""Scheduled jobs (CLAUDE.md section 5). GitHub Actions calls /internal/jobs/<run> on a schedule; each run
is a list of tasks. Every task must be idempotent: running it twice, or late, changes nothing extra.

Later phases add their tasks here:
- daily: pack expiry and carry-forward (phase 6), strike expiry (phase 7)
- frequent (every 30 minutes, 6 am to midnight IST): overdue check-out alerts (phase 8), payouts-due
  alerts (phase 9). Keep these quick.
"""

from collections.abc import Callable

from sqlalchemy import Connection, text

Task = Callable[[Connection], None]


def keep_database_active(conn: Connection) -> None:
    """A tiny query, so the free staging database isn't paused after a week without use."""
    conn.execute(text("SELECT 1"))


RUNS: dict[str, list[tuple[str, Task]]] = {
    "daily": [("keep_database_active", keep_database_active)],
    "frequent": [],
}
