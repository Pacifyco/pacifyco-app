"""Making a booking (CLAUDE.md 6.1 and 6.4; phase 6 "Book this sitter").

The parent picks one live sitter, so the plan is her level. A booking is whole hours, starts at least
4 hours from now (Reuben, 2026-11-17), fits inside one of her free times in the next 14 days, ends by
the plan's latest end and doesn't overlap a booking of hers that's confirmed. It's `pending_payment`
until an admin confirms the payment. Slots aren't held while payment is pending (decided 2026-11-03), so
only confirmed bookings take time away.

Not yet checked here, because what they need comes later in phase 6 and 7: money owed (payments) and
strikes.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import (
    Booking,
    BookingChild,
    BookingHomeInfo,
    BookingStatus,
    Child,
    Profile,
    Sitter,
)
from app.models import SitterLevel as Plan
from app.services import audit, availability, checklists, legal, pricing, search
from app.services.availability import INDIA, FreeTime

MIN_NOTICE = timedelta(hours=4)  # Reuben, 2026-11-17: time to pay before the 3-hour deadline
PAYMENT_DEADLINE = timedelta(hours=3)  # unpaid bookings are cancelled 3 hours before the start (6.1)
MAX_CHILDREN = 10
MIN_AGE_MONTHS = 18  # 6.4

# The plan's latest end, overtime included (6.1), as time after the start day's midnight in India.
LATEST_END: dict[Plan, timedelta] = {
    Plan.pause: timedelta(hours=18),
    Plan.unwind: timedelta(hours=22, minutes=30),
    Plan.recharge: timedelta(hours=24),
}
BATH_TIME: dict[Plan, bool] = {Plan.pause: False, Plan.unwind: True, Plan.recharge: True}

# Bookings that hold the sitter's time.
HOLDS_TIME = (BookingStatus.confirmed, BookingStatus.in_progress)


def _hour_up(moment: datetime) -> datetime:
    """The next whole hour in India time (India is +05:30, so whole hours there aren't whole in UTC)."""
    local = moment.astimezone(INDIA)
    floor = local.replace(minute=0, second=0, microsecond=0)
    return floor if floor == local else floor + timedelta(hours=1)


def _hour_down(moment: datetime) -> datetime:
    return moment.astimezone(INDIA).replace(minute=0, second=0, microsecond=0)


def earliest_start(now: datetime) -> datetime:
    return _hour_up(now + MIN_NOTICE)


def _busy(db: Session, sitter_id: uuid.UUID, now: datetime) -> list[FreeTime]:
    rows = db.execute(
        select(Booking.starts_at, Booking.ends_at).where(
            Booking.sitter_id == sitter_id, Booking.status.in_(HOLDS_TIME), Booking.ends_at > now
        )
    )
    return [FreeTime(row.starts_at, row.ends_at) for row in rows]


def _minus(times: list[FreeTime], busy: list[FreeTime]) -> list[FreeTime]:
    for taken in busy:
        left: list[FreeTime] = []
        for item in times:
            if taken.ends_at <= item.starts_at or taken.starts_at >= item.ends_at:
                left.append(item)
                continue
            if item.starts_at < taken.starts_at:
                left.append(FreeTime(item.starts_at, taken.starts_at))
            if taken.ends_at < item.ends_at:
                left.append(FreeTime(taken.ends_at, item.ends_at))
        times = left
    return times


def bookable_times(db: Session, sitter: Sitter, now: datetime) -> list[FreeTime]:
    """Her free times a booking can start in, soonest first: split at India midnight, cut to her plan's
    latest end, from 4 hours from now, without her confirmed bookings, in whole hours, at least 1 hour."""
    earliest = earliest_start(now)
    latest_end = LATEST_END[sitter.level]
    times = _minus(availability.free_times(db, sitter.profile_id, now), _busy(db, sitter.profile_id, now))
    result: list[FreeTime] = []
    for item in times:
        day = item.starts_at.astimezone(INDIA).date()
        while datetime.combine(day, time(), INDIA) < item.ends_at:
            midnight = datetime.combine(day, time(), INDIA)
            start = _hour_up(max(item.starts_at, midnight, earliest))
            end = _hour_down(min(item.ends_at, midnight + latest_end))
            if end - start >= timedelta(hours=1):
                result.append(FreeTime(start, end))
            day += timedelta(days=1)
    return result


def first_booking_with(db: Session, parent_id: uuid.UUID, sitter_id: uuid.UUID) -> bool:
    """No earlier booking with her that went ahead or is on its way: the "1-hour first booking" nudge (6.3)."""
    return not db.scalar(
        select(
            exists().where(
                Booking.parent_id == parent_id,
                Booking.sitter_id == sitter_id,
                Booking.status.in_((*HOLDS_TIME, BookingStatus.completed)),
            )
        )
    )


def _months_old(born: date, on: date) -> int:
    months = (on.year - born.year) * 12 + on.month - born.month
    return months - 1 if on.day < born.day else months


@dataclass(frozen=True)
class NewBooking:
    sitter_id: uuid.UUID
    starts_at: datetime
    hours: int
    child_ids: list[uuid.UUID]
    bath_time: bool
    cameras_on: bool
    camera_locations: str | None


def _check_time(db: Session, sitter: Sitter, starts_at: datetime, ends_at: datetime, now: datetime) -> None:
    local = starts_at.astimezone(INDIA)
    if (local.minute, local.second, local.microsecond) != (0, 0, 0):
        raise AppError(422, "whole_hours_only", "Bookings start on the hour.")
    if starts_at < earliest_start(now):
        raise AppError(422, "too_soon", "Bookings start at least 4 hours from now, so there's time to pay.")
    midnight = datetime.combine(local.date(), time(), INDIA)
    if ends_at > midnight + LATEST_END[sitter.level]:
        raise AppError(422, "past_latest_end", "This booking would end later than this sitter works.")
    if not availability.is_free(bookable_times(db, sitter, now), starts_at, ends_at):
        raise AppError(409, "not_free", "She isn't free for all of that time. Please choose another time.")


def _children(db: Session, parent_id: uuid.UUID, child_ids: list[uuid.UUID], day: date) -> list[Child]:
    if len(set(child_ids)) != len(child_ids):
        raise AppError(422, "child_repeated", "Each child can be added once.")
    if len(child_ids) > MAX_CHILDREN:
        raise AppError(422, "too_many_children", "Please choose fewer children.")
    children = list(db.scalars(select(Child).where(Child.parent_id == parent_id, Child.id.in_(child_ids))))
    if len(children) != len(child_ids):
        # Someone else's child, or one that doesn't exist: the same answer for both.
        raise AppError(404, "not_found", "We couldn't find that child on your profile.")
    for child in children:
        if _months_old(child.date_of_birth, day) < MIN_AGE_MONTHS:
            raise AppError(
                422, "child_too_young", f"Pacifyco looks after children from 18 months. {child.name} is younger."
            )
    return children


def create(db: Session, parent: Profile, new: NewBooking, now: datetime) -> Booking:
    checklists.require_finished_parent_profile(db, parent)
    legal.require_current_terms(db, parent)
    sitter = db.scalar(select(Sitter).where(Sitter.profile_id == new.sitter_id).with_for_update())
    if sitter is None or sitter.level is None:
        raise AppError(404, "not_found", "That sitter isn't available")
    # Live, the same check as her profile page.
    search.live_sitter(db, parent, new.sitter_id)

    price = pricing.booking_price_paise(sitter.level, len(new.child_ids), new.hours)
    starts_at = new.starts_at
    ends_at = starts_at + timedelta(hours=new.hours)
    _check_time(db, sitter, starts_at, ends_at, now)
    if new.bath_time and not BATH_TIME[sitter.level]:
        raise AppError(422, "no_bath_time", "Bath time isn't part of bookings with this sitter.")
    camera_locations = (new.camera_locations or "").strip() or None
    if new.cameras_on and camera_locations is None:
        raise AppError(422, "camera_locations_needed", "Please tell us where your cameras are.")
    children = _children(db, parent.id, new.child_ids, starts_at.astimezone(INDIA).date())

    booking = Booking(
        parent_id=parent.id,
        sitter_id=sitter.profile_id,
        starts_at=starts_at,
        ends_at=ends_at,
        plan=sitter.level,
        units=new.hours,
        children_count=len(children),
        price_paise=price,
        bath_time=new.bath_time,
        status=BookingStatus.pending_payment,
    )
    db.add(booking)
    db.flush()
    db.add_all(BookingChild(booking_id=booking.id, child_id=child.id) for child in children)
    db.add(
        BookingHomeInfo(
            booking_id=booking.id,
            cameras_on=new.cameras_on,
            camera_locations=camera_locations if new.cameras_on else None,
        )
    )
    audit.record(
        db,
        parent.id,
        "booking_created",
        "booking",
        str(booking.id),
        after={
            "status": booking.status.value,
            "sitter_id": str(sitter.profile_id),
            "starts_at": starts_at.isoformat(),
            "units": new.hours,
            "children_count": len(children),
            "price_paise": price,
        },
    )
    db.commit()
    return booking


def pay_by(booking: Booking) -> datetime:
    return booking.starts_at - PAYMENT_DEADLINE


def parents_booking(db: Session, parent_id: uuid.UUID, booking_id: uuid.UUID) -> Booking:
    """One of this parent's bookings; anyone else's is "not found"."""
    booking = db.scalar(select(Booking).where(Booking.id == booking_id, Booking.parent_id == parent_id))
    if booking is None:
        raise AppError(404, "not_found", "We couldn't find that booking.")
    return booking


def child_names(db: Session, booking_id: uuid.UUID) -> list[str]:
    return list(
        db.scalars(
            select(Child.name)
            .join(BookingChild, BookingChild.child_id == Child.id)
            .where(BookingChild.booking_id == booking_id)
            .order_by(Child.date_of_birth)
        )
    )


def home_info(db: Session, booking_id: uuid.UUID) -> BookingHomeInfo | None:
    return db.get(BookingHomeInfo, booking_id)
