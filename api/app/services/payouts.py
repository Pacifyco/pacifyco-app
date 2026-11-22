"""The admin payouts-due list (CLAUDE.md 6.10; phase 9).

Every released, unpaid earning, grouped by sitter (one transfer for everything due to her; Reuben,
2026-11-22), soonest deadline first, with how she's paid. Showing a sitter's bank details writes an audit
row each time (Reuben, 2026-11-22), as viewing a health disclosure does. The banner on the admin home page
uses `summary`, which shows no details and logs nothing.
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import String, cast, exists, func, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import AuditLog, Booking, EarningStatus, Payout, Profile, Sitter, SitterEarning
from app.services import audit, sitters


@dataclass
class DueEarning:
    earning: SitterEarning
    booking: Booking


@dataclass
class SitterDue:
    sitter: Sitter
    profile: Profile
    bank: sitters.BankDetails | None
    earnings: list[DueEarning] = field(default_factory=list)

    @property
    def total_paise(self) -> int:
        return sum(item.earning.amount_paise for item in self.earnings)

    @property
    def next_due_by(self) -> datetime:
        return min(item.earning.due_by for item in self.earnings if item.earning.due_by is not None)


def due(db: Session, admin_id: uuid.UUID, encryption_key: str) -> list[SitterDue]:
    """What's due, by sitter. Logs a `bank_details_viewed` audit row for each sitter whose bank details
    are shown."""
    found = db.execute(
        select(SitterEarning, Booking)
        .join(Booking, Booking.id == SitterEarning.booking_id)
        .where(SitterEarning.status == EarningStatus.released)
        # Same deadline (written together at check-out): booking pay, then overtime, then a fee.
        .order_by(SitterEarning.due_by, SitterEarning.kind, SitterEarning.created_at)
    ).all()
    by_sitter: dict[uuid.UUID, SitterDue] = {}
    for earning, booking in found:
        group = by_sitter.get(earning.sitter_id)
        if group is None:
            sitter = db.get(Sitter, earning.sitter_id)
            profile = db.get(Profile, earning.sitter_id)
            assert sitter is not None and profile is not None
            bank = sitters.get_payout_bank(db, sitter.profile_id, encryption_key)
            group = by_sitter[earning.sitter_id] = SitterDue(sitter, profile, bank)
        group.earnings.append(DueEarning(earning, booking))
    for group in by_sitter.values():
        if group.bank is not None:
            audit.record(db, admin_id, "bank_details_viewed", "sitters", str(group.sitter.profile_id))
    db.commit()
    return sorted(by_sitter.values(), key=lambda group: group.next_due_by)


@dataclass(frozen=True)
class Summary:
    due: int  # released, unpaid earnings
    overdue: int  # of those, past their 12-hour deadline


def summary(db: Session, now: datetime) -> Summary:
    released = SitterEarning.status == EarningStatus.released
    total = db.scalar(select(func.count()).select_from(SitterEarning).where(released)) or 0
    overdue = db.scalar(select(func.count()).select_from(SitterEarning).where(released, SitterEarning.due_by < now))
    return Summary(total, overdue or 0)


# ---------- marking a payout paid (6.10) ----------

REFERENCE = re.compile(r"[A-Za-z0-9]{6,35}")  # a UPI reference (12 digits) or a bank UTR


def mark_paid(
    db: Session, admin_id: uuid.UUID, sitter_id: uuid.UUID, earning_ids: list[uuid.UUID], reference: str
) -> Payout:
    """One transfer for the earnings the admin paid (the ones shown on the list, so nothing released since
    is marked paid by mistake), recorded with its reference. The earnings become paid. Commits."""
    reference = reference.strip().upper()
    if not REFERENCE.fullmatch(reference):
        raise AppError(422, "invalid_reference", "Enter the UPI reference or bank transfer reference (UTR).")
    sitter = db.get(Sitter, sitter_id)
    if sitter is None:
        raise AppError(404, "not_found", "We couldn't find that sitter.")
    if sitter.payout_method is None:
        raise AppError(409, "no_payout_details", "She hasn't given payout details yet.")
    ids = set(earning_ids)
    earnings = db.scalars(select(SitterEarning).where(SitterEarning.id.in_(ids)).with_for_update()).all()
    if (
        not ids
        or len(earnings) != len(ids)
        or any(item.sitter_id != sitter_id or item.status != EarningStatus.released for item in earnings)
    ):
        raise AppError(409, "payout_changed", "What's due has changed. Reload the list and check it again.")
    if db.scalar(select(Payout.id).where(Payout.transfer_reference == reference)) is not None:
        raise AppError(409, "reference_used", "That reference has already been used for a payout.")
    payout = Payout(
        sitter_id=sitter_id,
        amount_paise=sum(item.amount_paise for item in earnings),
        method=sitter.payout_method,
        transfer_reference=reference,
        paid_by=admin_id,
    )
    db.add(payout)
    db.flush()
    for earning in earnings:
        earning.status = EarningStatus.paid
        earning.payout_id = payout.id
        audit.record(
            db,
            admin_id,
            "earning_paid",
            "sitter_earning",
            str(earning.id),
            before={"status": "released"},
            after={"status": "paid", "payout_id": str(payout.id)},
        )
    audit.record(
        db,
        admin_id,
        "payout_paid",
        "payout",
        str(payout.id),
        after={
            "sitter_id": str(sitter_id),
            "amount_paise": payout.amount_paise,
            "method": payout.method.value,
            "earning_ids": sorted(str(item.id) for item in earnings),
        },
    )
    db.commit()
    return payout


# ---------- alerts (6.10): under 3 hours left, and overdue ----------

DUE_SOON = timedelta(hours=3)
DUE_SOON_ALERTED = "payout_due_soon_alerted"
OVERDUE_ALERTED = "payout_overdue_alerted"


def _not_alerted(db: Session, action: str, *conditions) -> list[SitterEarning]:
    alerted = exists().where(
        AuditLog.action == action,
        AuditLog.entity == "sitter_earning",
        AuditLog.entity_id == cast(SitterEarning.id, String),
    )
    return list(
        db.scalars(
            select(SitterEarning)
            .where(SitterEarning.status == EarningStatus.released, *conditions, ~alerted)
            .order_by(SitterEarning.due_by)
        )
    )


def due_soon_not_alerted(db: Session, now: datetime) -> list[SitterEarning]:
    """Released, unpaid, under 3 hours left, not yet alerted. (An earning held again by an incident and
    released later isn't alerted a second time.)"""
    return _not_alerted(db, DUE_SOON_ALERTED, SitterEarning.due_by > now, SitterEarning.due_by <= now + DUE_SOON)


def overdue_not_alerted(db: Session, now: datetime) -> list[SitterEarning]:
    return _not_alerted(db, OVERDUE_ALERTED, SitterEarning.due_by <= now)


def mark_alerted(db: Session, action: str, found: list[SitterEarning]) -> None:
    """Remembers each alert in the audit log, so none is sent twice. The caller commits."""
    for earning in found:
        audit.record(db, None, action, "sitter_earning", str(earning.id), after={"due_by": earning.due_by.isoformat()})
