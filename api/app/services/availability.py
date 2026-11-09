"""A sitter's free times (CLAUDE.md 6.4: a booking must fit inside the sitter's availability).

Decided 2026-11-09: she sets a week that repeats (whole hours, India time) and marks single days off.
Her free times are worked out from those for the next BOOK_AHEAD_DAYS days, which is also how far
ahead parents can book."""

import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import DayOff, Sitter, WeeklyHours

INDIA = ZoneInfo("Asia/Kolkata")
BOOK_AHEAD_DAYS = 14  # parents see and book free times up to two weeks ahead (decided 2026-11-09)
MAX_DAYS_OFF_AHEAD = 365


@dataclass(frozen=True)
class Hours:
    weekday: int  # 0 = Monday
    start_hour: int  # 0-23
    end_hour: int  # 1-24; 24 is midnight at the end of the day


@dataclass(frozen=True)
class FreeTime:
    starts_at: datetime
    ends_at: datetime


def today_in_india(now: datetime) -> date:
    return now.astimezone(INDIA).date()


def week(db: Session, sitter_id: uuid.UUID) -> list[Hours]:
    rows = db.scalars(
        select(WeeklyHours)
        .where(WeeklyHours.sitter_id == sitter_id)
        .order_by(WeeklyHours.weekday, WeeklyHours.start_hour)
    )
    return [Hours(row.weekday, row.start_hour, row.end_hour) for row in rows]


def set_week(db: Session, sitter_id: uuid.UUID, hours: list[Hours]) -> list[Hours]:
    """Replaces her whole week. Times on one day may touch (9-1 and 1-5) but not overlap.
    Bookings (phase 7) will keep already-booked times whatever the new week says."""
    by_day: dict[int, list[Hours]] = defaultdict(list)
    for item in hours:
        if not (0 <= item.weekday <= 6 and 0 <= item.start_hour <= 23 and 1 <= item.end_hour <= 24):
            raise AppError(422, "hours_invalid", "Choose a day and whole hours")
        if item.end_hour <= item.start_hour:
            raise AppError(422, "hours_order", "Each time must end after it starts")
        by_day[item.weekday].append(item)
    for items in by_day.values():
        items.sort(key=lambda item: item.start_hour)
        for earlier, later in zip(items, items[1:], strict=False):
            if later.start_hour < earlier.end_hour:
                raise AppError(422, "hours_overlap", "Two times on the same day overlap")

    # Lock her row so two saves at once can't interleave.
    db.scalar(select(Sitter).where(Sitter.profile_id == sitter_id).with_for_update())
    db.execute(delete(WeeklyHours).where(WeeklyHours.sitter_id == sitter_id))
    for item in sorted(hours, key=lambda item: (item.weekday, item.start_hour)):
        db.add(
            WeeklyHours(sitter_id=sitter_id, weekday=item.weekday, start_hour=item.start_hour, end_hour=item.end_hour)
        )
    db.commit()
    return week(db, sitter_id)


def days_off(db: Session, sitter_id: uuid.UUID, today: date) -> list[date]:
    return list(
        db.scalars(select(DayOff.day).where(DayOff.sitter_id == sitter_id, DayOff.day >= today).order_by(DayOff.day))
    )


def add_day_off(db: Session, sitter_id: uuid.UUID, day: date, today: date) -> None:
    """Marking the same day twice is fine. Bookings (phase 7) will need her to cancel first."""
    if day < today:
        raise AppError(422, "day_in_the_past", "Choose today or a later day")
    if day > today + timedelta(days=MAX_DAYS_OFF_AHEAD):
        raise AppError(422, "day_too_far", "Choose a day within the next year")
    if db.get(DayOff, (sitter_id, day)) is None:
        db.add(DayOff(sitter_id=sitter_id, day=day))
        db.commit()


def remove_day_off(db: Session, sitter_id: uuid.UUID, day: date) -> None:
    # Keyed by her own id, so she can only ever remove her own days off.
    found = db.get(DayOff, (sitter_id, day))
    if found is None:
        raise AppError(404, "not_found", "That day isn't marked as a day off")
    db.delete(found)
    db.commit()


def _merge(times: list[FreeTime]) -> list[FreeTime]:
    """Joins times that touch (Mon 6 pm-midnight and Tue midnight-2 am become one)."""
    merged: list[FreeTime] = []
    for item in sorted(times, key=lambda item: item.starts_at):
        if merged and item.starts_at <= merged[-1].ends_at:
            last = merged[-1]
            merged[-1] = FreeTime(last.starts_at, max(last.ends_at, item.ends_at))
        else:
            merged.append(item)
    return merged


def free_times_for(db: Session, sitter_ids: Iterable[uuid.UUID], now: datetime) -> dict[uuid.UUID, list[FreeTime]]:
    """Each sitter's free times from now until the end of the booking window, soonest first.
    A time that has started is kept (it still has time left); one that has ended is not."""
    ids = list(sitter_ids)
    result: dict[uuid.UUID, list[FreeTime]] = {sitter_id: [] for sitter_id in ids}
    if not ids:
        return result
    today = today_in_india(now)
    last_day = today + timedelta(days=BOOK_AHEAD_DAYS - 1)
    hours: dict[uuid.UUID, list[WeeklyHours]] = defaultdict(list)
    for row in db.scalars(select(WeeklyHours).where(WeeklyHours.sitter_id.in_(ids))):
        hours[row.sitter_id].append(row)
    off: dict[uuid.UUID, set[date]] = defaultdict(set)
    for sitter_id, day in db.execute(
        select(DayOff.sitter_id, DayOff.day).where(
            DayOff.sitter_id.in_(ids), DayOff.day >= today, DayOff.day <= last_day
        )
    ):
        off[sitter_id].add(day)

    for sitter_id in ids:
        times: list[FreeTime] = []
        for offset in range(BOOK_AHEAD_DAYS):
            day = today + timedelta(days=offset)
            if day in off[sitter_id]:
                continue
            midnight = datetime.combine(day, time(), INDIA)
            for row in hours[sitter_id]:
                if row.weekday != day.weekday():
                    continue
                ends_at = midnight + timedelta(hours=row.end_hour)
                if ends_at > now:
                    times.append(FreeTime(midnight + timedelta(hours=row.start_hour), ends_at))
        result[sitter_id] = _merge(times)
    return result


def free_times(db: Session, sitter_id: uuid.UUID, now: datetime) -> list[FreeTime]:
    return free_times_for(db, [sitter_id], now)[sitter_id]


def is_free(times: list[FreeTime], starts_at: datetime, ends_at: datetime) -> bool:
    """Whether one free time covers the whole of this time (for search now, bookings in phase 7)."""
    return any(item.starts_at <= starts_at and item.ends_at >= ends_at for item in times)


def has_time_on(times: list[FreeTime], day: date, now: datetime) -> bool:
    """Whether any free time is left on this India day."""
    day_start = max(datetime.combine(day, time(), INDIA), now)
    day_end = datetime.combine(day, time(), INDIA) + timedelta(days=1)
    return any(item.starts_at < day_end and item.ends_at > day_start for item in times)
