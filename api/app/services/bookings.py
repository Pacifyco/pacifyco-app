"""Making a booking (CLAUDE.md 6.1 and 6.4; phase 6 "Book this sitter").

The parent picks one live sitter, so the plan is her level. A booking is whole hours, starts at least
4 hours from now (Reuben, 2026-11-17), fits inside one of her free times in the next 14 days, ends by
the plan's latest end and doesn't overlap a booking of hers that's confirmed. It's `pending_payment`
until an admin confirms the payment. Slots aren't held while payment is pending (decided 2026-11-03), so
only confirmed bookings take time away.

The parent must have accepted the current terms, finished their profile, live inside the service
area and owe nothing (`require_can_book`). Strikes aren't checked yet: they come in phase 7.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import (
    Booking,
    BookingChild,
    BookingHomeInfo,
    BookingStatus,
    Child,
    LegalAcceptance,
    Payment,
    PaymentKind,
    PaymentStatus,
    Profile,
    Sitter,
    VerificationStatus,
)
from app.models import SitterLevel as Plan
from app.services import audit, availability, checklists, legal, pricing, search, service_area
from app.services.availability import INDIA, FreeTime

# Reuben, 2026-11-19 (was 4 hours): time for the sitter to answer and the parent to pay (6.1, 6.4).
MIN_NOTICE = timedelta(hours=6)
# A request: the sitter has 5 hours from when she can see it to answer, and it lapses 4 hours before
# the start if that's sooner, leaving the parent an hour to pay (Reuben, 2026-11-19).
ANSWER_WITHIN = timedelta(hours=5)
ANSWER_CUTOFF = timedelta(hours=4)
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

# Bookings that hold the sitter's time: once she accepts a request it's held while the parent pays
# (`pending_payment`, Reuben 2026-11-19). A request she hasn't answered doesn't hold it, nor does an older
# paid booking waiting for a child's verification (`awaiting_verification`, Reuben 2026-11-18).
HOLDS_TIME = (BookingStatus.pending_payment, BookingStatus.confirmed, BookingStatus.in_progress)


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
        raise AppError(
            422, "too_soon", "Bookings start at least 6 hours from now, so the sitter can answer and you can pay."
        )
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


def require_terms_then_profile(db: Session, parent: Profile) -> None:
    """A parent who accepted earlier terms and now has a new version to accept hears exactly that
    (`terms_required`, 7); anyone else still filling in their profile hears "finish your profile" (the
    terms are part of its consent step)."""
    accepted_before = db.scalar(select(exists().where(LegalAcceptance.profile_id == parent.id)))
    if accepted_before:
        legal.require_current_terms(db, parent)
    checklists.require_finished_parent_profile(db, parent)
    service_area.require_in_service_area(db, parent.pin_code or "")


# Charges a parent must pay after a booking (6.5 and 6.8): unpaid, they're money owed.
OWED_KINDS = (PaymentKind.overtime, PaymentKind.cancellation_charge)


def amount_owed(db: Session, parent_id: uuid.UUID) -> int:
    """What the parent still owes Pacifyco, in paise: their unpaid charges (CLAUDE.md 6.4, 6.8). Booking
    payments aren't owed money (the full price is paid before a booking goes ahead), and refunds are
    money Pacifyco owes them."""
    return db.scalar(
        select(func.coalesce(func.sum(Payment.amount_paise), 0)).where(
            Payment.parent_id == parent_id, Payment.kind.in_(OWED_KINDS), Payment.status == PaymentStatus.pending
        )
    )


def require_nothing_owed(db: Session, parent_id: uuid.UUID) -> None:
    if amount_owed(db, parent_id) > 0:
        raise AppError(409, "money_owed", "Please pay what you owe Pacifyco first. You'll find it under Your payments.")


def require_can_book(db: Session, parent: Profile) -> None:
    """The parent may book at all (6.4, 6.13, 7): the current terms accepted, the profile finished, a
    home inside the service area (1) and nothing owed."""
    require_terms_then_profile(db, parent)
    require_nothing_owed(db, parent.id)


def create(db: Session, parent: Profile, new: NewBooking, now: datetime) -> Booking:
    require_can_book(db, parent)
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
        status=BookingStatus.requested,
        # The sitter sees it only once every child on it is verified (6.4).
        request_visible_at=now
        if all(child.verification_status == VerificationStatus.approved for child in children)
        else None,
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


# Bookings still on their way: listed under "Upcoming" until they end.
ON_THE_WAY = (
    BookingStatus.requested,
    BookingStatus.pending_payment,
    BookingStatus.awaiting_verification,
    BookingStatus.confirmed,
    BookingStatus.in_progress,
)


def parents_bookings(db: Session, parent_id: uuid.UUID, now: datetime) -> tuple[list[Booking], list[Booking]]:
    """The parent's bookings: upcoming ones (on their way and not yet ended) soonest first, and the rest
    (ended or cancelled) most recent first."""
    found = db.scalars(select(Booking).where(Booking.parent_id == parent_id)).all()
    upcoming = sorted(
        (item for item in found if item.status in ON_THE_WAY and item.ends_at > now), key=lambda item: item.starts_at
    )
    taken = {item.id for item in upcoming}
    past = sorted((item for item in found if item.id not in taken), key=lambda item: item.starts_at, reverse=True)
    return upcoming, past


# What a sitter sees in her bookings (6.4): the ones she accepted (waiting for payment, then confirmed),
# never an older one waiting for a child's verification or cancelled before she accepted it. Requests
# waiting for her answer are listed apart (`requests_for`).
SITTER_SEES = (
    BookingStatus.pending_payment,
    BookingStatus.cancelled_unpaid,
    BookingStatus.confirmed,
    BookingStatus.in_progress,
    BookingStatus.completed,
    BookingStatus.cancelled_parent,
    BookingStatus.cancelled_parent_late,
    BookingStatus.cancelled_sitter,
    BookingStatus.cancelled_sitter_late,
    BookingStatus.parent_absent,
    BookingStatus.sitter_no_show,
)
SITTER_UPCOMING = (BookingStatus.pending_payment, BookingStatus.confirmed, BookingStatus.in_progress)
# The home address and the family's emergency contact: only once it's confirmed (paid), while ahead.
ADDRESS_SHOWN = (BookingStatus.confirmed, BookingStatus.in_progress)


def sitters_bookings(db: Session, sitter_id: uuid.UUID, now: datetime) -> tuple[list[Booking], list[Booking]]:
    """The sitter's confirmed bookings: upcoming ones (not yet ended) soonest first, and the rest most
    recent first."""
    found = db.scalars(select(Booking).where(Booking.sitter_id == sitter_id, Booking.status.in_(SITTER_SEES))).all()
    upcoming = sorted(
        (item for item in found if item.status in SITTER_UPCOMING and item.ends_at > now),
        key=lambda item: item.starts_at,
    )
    taken = {item.id for item in upcoming}
    past = sorted((item for item in found if item.id not in taken), key=lambda item: item.starts_at, reverse=True)
    return upcoming, past


def _she_sees():
    """Her bookings, and requests she can see (every child verified)."""
    return or_(
        Booking.status.in_(SITTER_SEES),
        and_(Booking.status == BookingStatus.requested, Booking.request_visible_at.is_not(None)),
    )


def sitters_booking(db: Session, sitter_id: uuid.UUID, booking_id: uuid.UUID) -> Booking:
    """One of her bookings or requests she can see (6.4); anything else, or anyone else's, is "not
    found"."""
    booking = db.scalar(select(Booking).where(Booking.id == booking_id, Booking.sitter_id == sitter_id, _she_sees()))
    if booking is None:
        raise AppError(404, "not_found", "We couldn't find that booking.")
    return booking


def children_on(db: Session, booking_id: uuid.UUID) -> list[Child]:
    """The children on a booking, eldest first."""
    return list(
        db.scalars(
            select(Child)
            .join(BookingChild, BookingChild.child_id == Child.id)
            .where(BookingChild.booking_id == booking_id)
            .order_by(Child.date_of_birth)
        )
    )


def months_old_at_start(born: date, booking: Booking) -> int:
    """A child's age in whole months on the booking's day (India time)."""
    return _months_old(born, booking.starts_at.astimezone(INDIA).date())


def child_names_for(db: Session, booking_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    """Each booking's children's names, eldest first, in one query."""
    names: dict[uuid.UUID, list[str]] = {booking_id: [] for booking_id in booking_ids}
    if not booking_ids:
        return names
    rows = db.execute(
        select(BookingChild.booking_id, Child.name)
        .join(Child, BookingChild.child_id == Child.id)
        .where(BookingChild.booking_id.in_(booking_ids))
        .order_by(Child.date_of_birth)
    )
    for booking_id, name in rows:
        names[booking_id].append(name)
    return names


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


# ---------- requests: the sitter answers before the parent pays (6.4; Reuben, 2026-11-19) ----------


def answer_by(booking: Booking) -> datetime:
    """When an unanswered request lapses: 5 hours after she could see it, or 4 hours before the start if
    that's sooner (and then too if she never could see it)."""
    cutoff = booking.starts_at - ANSWER_CUTOFF
    if booking.request_visible_at is None:
        return cutoff
    return min(booking.request_visible_at + ANSWER_WITHIN, cutoff)


def requests_for(db: Session, sitter_id: uuid.UUID) -> list[Booking]:
    """Requests waiting for her answer that she can see, the one to answer soonest first."""
    found = db.scalars(
        select(Booking).where(
            Booking.sitter_id == sitter_id,
            Booking.status == BookingStatus.requested,
            Booking.request_visible_at.is_not(None),
        )
    ).all()
    return sorted(found, key=answer_by)


def lapse_requests(
    db: Session,
    now: datetime,
    booking_id: uuid.UUID | None = None,
    parent_id: uuid.UUID | None = None,
    sitter_id: uuid.UUID | None = None,
) -> list[uuid.UUID]:
    """Requests not answered in time lapse (`request_lapsed`). Idempotent; the caller commits. Returns
    their ids, so the parents can be told."""
    query = select(Booking.id, Booking.status).where(
        Booking.status == BookingStatus.requested,
        or_(
            Booking.starts_at - ANSWER_CUTOFF <= now,
            and_(Booking.request_visible_at.is_not(None), Booking.request_visible_at + ANSWER_WITHIN <= now),
        ),
    )
    for column, value in ((Booking.id, booking_id), (Booking.parent_id, parent_id), (Booking.sitter_id, sitter_id)):
        if value is not None:
            query = query.where(column == value)
    found = list(db.execute(query.with_for_update(skip_locked=True)))
    return _cancel(db, found, BookingStatus.request_lapsed, {"reason": "not_answered_in_time"})


def make_visible(db: Session, parent_id: uuid.UUID, now: datetime) -> list[uuid.UUID]:
    """After a child is approved: this parent's requests whose children are now all verified reach their
    sitters, whose 5 hours to answer start now. Returns their ids (so the sitters can be told). The
    caller commits."""
    waiting = db.scalars(
        select(Booking)
        .where(
            Booking.parent_id == parent_id,
            Booking.status == BookingStatus.requested,
            Booking.request_visible_at.is_(None),
            Booking.starts_at - ANSWER_CUTOFF > now,
        )
        .with_for_update()
    ).all()
    shown = []
    for booking in waiting:
        if children_verified(db, booking.id):
            booking.request_visible_at = now
            shown.append(booking.id)
    return shown


def _open_request(db: Session, sitter_id: uuid.UUID, booking_id: uuid.UUID, now: datetime) -> Booking:
    lapse_requests(db, now, booking_id=booking_id)
    # A request she could see, whatever has happened to it since, so a second answer is told why.
    seen = or_(_she_sees(), Booking.request_visible_at.is_not(None))
    booking = db.scalar(
        select(Booking).where(Booking.id == booking_id, Booking.sitter_id == sitter_id, seen).with_for_update()
    )
    if booking is None:
        raise AppError(404, "not_found", "We couldn't find that request.")
    if booking.status == BookingStatus.request_lapsed:
        db.commit()
        raise AppError(409, "request_lapsed", "This request has lapsed: it wasn't answered in time.")
    if booking.status != BookingStatus.requested:
        raise AppError(409, "already_answered", "You've already answered this request.")
    return booking


@dataclass(frozen=True)
class Accepted:
    booking: Booking
    # Other parents' requests for an overlapping time, declined because she accepted this one.
    declined: list[uuid.UUID]


def accept(db: Session, sitter_id: uuid.UUID, booking_id: uuid.UUID, now: datetime) -> Accepted:
    """She can do it: her time is held while the parent pays (`pending_payment`), and other requests
    for an overlapping time are declined (Reuben, 2026-11-19)."""
    # Her own row first, so two accepts for her at once take turns.
    db.execute(select(Sitter.profile_id).where(Sitter.profile_id == sitter_id).with_for_update())
    booking = _open_request(db, sitter_id, booking_id, now)
    if slot_taken(db, booking):
        raise AppError(409, "time_taken", "You've already accepted a booking for this time.")
    audit.record(
        db,
        sitter_id,
        "request_accepted",
        "booking",
        str(booking.id),
        before={"status": booking.status.value},
        after={"status": BookingStatus.pending_payment.value},
    )
    booking.status = BookingStatus.pending_payment
    db.flush()
    others = list(
        db.execute(
            select(Booking.id, Booking.status)
            .where(
                Booking.sitter_id == sitter_id,
                Booking.id != booking.id,
                Booking.status == BookingStatus.requested,
                Booking.starts_at < booking.ends_at,
                Booking.ends_at > booking.starts_at,
            )
            .with_for_update()
        )
    )
    declined = _cancel(
        db, others, BookingStatus.request_declined, {"reason": "time_taken", "taken_by": str(booking.id)}
    )
    db.commit()
    return Accepted(booking, declined)


def decline(db: Session, sitter_id: uuid.UUID, booking_id: uuid.UUID, now: datetime) -> Booking:
    """She can't do it. No penalty; the parent is told and can book someone else."""
    booking = _open_request(db, sitter_id, booking_id, now)
    audit.record(
        db,
        sitter_id,
        "request_declined",
        "booking",
        str(booking.id),
        before={"status": booking.status.value},
        after={"status": BookingStatus.request_declined.value},
    )
    booking.status = BookingStatus.request_declined
    db.commit()
    return booking


# ---------- Pacifyco's own cancellations of unpaid bookings (6.1 and 6.4) ----------

# A booking payment that, once sent in time, keeps the booking for an admin to decide (Reuben,
# 2026-11-18): a rejected one doesn't.
KEEPS_BOOKING = (PaymentStatus.pending, PaymentStatus.confirmed)


def _cancel(db: Session, found: list, status: BookingStatus, reason: dict) -> list[uuid.UUID]:
    """Cancels the bookings in `found` (rows of id and status). Paid ones (`awaiting_verification`) are
    owed a full refund (Reuben, 2026-11-18). Returns their ids."""
    # Read before the update, which also changes any of these bookings already loaded in the session.
    earlier = [(item.id, item.status) for item in found]
    ids = [booking_id for booking_id, _ in earlier]
    if not ids:
        return ids
    db.execute(update(Booking).where(Booking.id.in_(ids)).values(status=status))
    for booking_id, was in earlier:
        audit.record(
            db,
            None,  # Pacifyco itself, not a person
            "booking_cancelled",
            "booking",
            str(booking_id),
            before={"status": was.value},
            after={"status": status.value, **reason},
        )
        if was == BookingStatus.awaiting_verification:
            refund_booking(db, None, booking_id)
    return ids


def cancel_unpaid(
    db: Session, now: datetime, booking_id: uuid.UUID | None = None, parent_id: uuid.UUID | None = None
) -> list[uuid.UUID]:
    """Cancels `pending_payment` bookings whose payment deadline (3 hours before the start) has passed
    with no payment sent (6.1). A booking whose UPI reference was sent in time waits for an admin, who
    confirms or rejects it (Reuben, 2026-11-18). Idempotent; the caller commits. With `booking_id`, only
    that booking (so a booking opened before the next job run already shows as cancelled)."""
    paid = exists().where(
        Payment.booking_id == Booking.id, Payment.kind == PaymentKind.booking, Payment.status.in_(KEEPS_BOOKING)
    )
    query = select(Booking.id, Booking.status).where(
        Booking.status == BookingStatus.pending_payment,
        Booking.starts_at <= now + PAYMENT_DEADLINE,
        ~paid,
    )
    if booking_id is not None:
        query = query.where(Booking.id == booking_id)
    if parent_id is not None:
        query = query.where(Booking.parent_id == parent_id)
    # Rows another transaction holds (a payment being sent or confirmed right now) are left for the
    # next run.
    found = list(db.execute(query.with_for_update(skip_locked=True)))
    return _cancel(db, found, BookingStatus.cancelled_unpaid, {"reason": "not_paid_by_deadline"})


def cancel_unverified(
    db: Session, now: datetime, booking_id: uuid.UUID | None = None, parent_id: uuid.UUID | None = None
) -> list[uuid.UUID]:
    """Paid bookings whose start has come while a child on them still isn't verified (or was rejected)
    can't go ahead: cancelled (`cancelled_unverified`) and refunded in full (Reuben, 2026-11-18).
    Idempotent; the caller commits. With `booking_id`, only that booking."""
    query = select(Booking.id, Booking.status).where(
        Booking.status == BookingStatus.awaiting_verification, Booking.starts_at <= now
    )
    if booking_id is not None:
        query = query.where(Booking.id == booking_id)
    if parent_id is not None:
        query = query.where(Booking.parent_id == parent_id)
    found = list(db.execute(query.with_for_update(skip_locked=True)))
    return _cancel(db, found, BookingStatus.cancelled_unverified, {"reason": "children_not_verified_by_start"})


def cancel_overlapping(db: Session, confirmed: Booking) -> list[uuid.UUID]:
    """Once a booking is confirmed it takes her time: every other booking with her for an overlapping
    time that is still a request, unpaid (`pending_payment`, from before requests) or paid but waiting for
    a child's verification (`awaiting_verification`, refunded) is cancelled (6.4). The caller commits."""
    found = list(
        db.execute(
            select(Booking.id, Booking.status)
            .where(
                Booking.sitter_id == confirmed.sitter_id,
                Booking.id != confirmed.id,
                Booking.status.in_(
                    (BookingStatus.requested, BookingStatus.pending_payment, BookingStatus.awaiting_verification)
                ),
                Booking.starts_at < confirmed.ends_at,
                Booking.ends_at > confirmed.starts_at,
            )
            .with_for_update()
        )
    )
    return _cancel(db, found, BookingStatus.cancelled_slot_taken, {"taken_by": str(confirmed.id)})


# ---------- refunds (6.1) ----------


def owe_refund(db: Session, actor_id: uuid.UUID | None, paid: Payment) -> Payment:
    """Money received for a booking that won't go ahead is paid back (6.1): a pending refund row for the
    full amount, for an admin to pay by UPI or bank transfer and mark paid."""
    refund = Payment(
        booking_id=paid.booking_id,
        parent_id=paid.parent_id,
        kind=PaymentKind.refund,
        amount_paise=-paid.amount_paise,
        status=PaymentStatus.pending,
    )
    db.add(refund)
    db.flush()
    audit.record(
        db,
        actor_id,
        "refund_owed",
        "payment",
        str(refund.id),
        after={"booking_id": str(paid.booking_id), "amount_paise": refund.amount_paise, "for_payment": str(paid.id)},
    )
    return refund


def refund_booking(db: Session, actor_id: uuid.UUID | None, booking_id: uuid.UUID) -> list[Payment]:
    """A refund for each confirmed booking payment of a booking that won't go ahead."""
    paid = db.scalars(
        select(Payment).where(
            Payment.booking_id == booking_id,
            Payment.kind == PaymentKind.booking,
            Payment.status == PaymentStatus.confirmed,
        )
    ).all()
    return [owe_refund(db, actor_id, payment) for payment in paid]


# ---------- once paid (6.1 and 6.4) ----------


def children_verified(db: Session, booking_id: uuid.UUID) -> bool:
    """Every child on the booking has an approved birth certificate (7)."""
    return not db.scalar(
        select(
            exists().where(
                BookingChild.booking_id == booking_id,
                BookingChild.child_id == Child.id,
                Child.verification_status != VerificationStatus.approved,
            )
        )
    )


# Bookings that have won her time for good: when a payment is confirmed, only these count as having
# taken it (an older booking still waiting for payment doesn't, 6.4).
CONFIRMED = (BookingStatus.confirmed, BookingStatus.in_progress)


def slot_taken(db: Session, booking: Booking, holding: tuple = HOLDS_TIME) -> bool:
    """Another booking with her for an overlapping time already holds it."""
    return bool(
        db.scalar(
            select(
                exists().where(
                    Booking.sitter_id == booking.sitter_id,
                    Booking.id != booking.id,
                    Booking.status.in_(holding),
                    Booking.starts_at < booking.ends_at,
                    Booking.ends_at > booking.starts_at,
                )
            )
        )
    )


def mark_paid(db: Session, admin_id: uuid.UUID, booking: Booking) -> list[uuid.UUID]:
    """The booking's payment is confirmed: `confirmed` if every child on it is verified, and then other
    bookings for an overlapping time with her are cancelled (their ids are returned). Otherwise it's
    `awaiting_verification` and doesn't hold her time yet (Reuben, 2026-11-18). The caller commits."""
    status = BookingStatus.confirmed if children_verified(db, booking.id) else BookingStatus.awaiting_verification
    audit.record(
        db,
        admin_id,
        "booking_paid",
        "booking",
        str(booking.id),
        before={"status": booking.status.value},
        after={"status": status.value},
    )
    booking.status = status
    db.flush()
    if status != BookingStatus.confirmed:
        return []
    return cancel_overlapping(db, booking)


@dataclass(frozen=True)
class AfterVerification:
    # This parent's paid bookings now confirmed.
    confirmed: list[uuid.UUID]
    # This parent's paid bookings whose time another booking took first: cancelled and refunded.
    lost: list[uuid.UUID]
    # Other bookings for the same time as a newly confirmed one, cancelled (paid ones refunded).
    cancelled: list[uuid.UUID]


def confirm_verified(db: Session, admin_id: uuid.UUID, parent_id: uuid.UUID, now: datetime) -> AfterVerification:
    """After a child is approved: this parent's paid bookings whose children are now all verified are
    confirmed and take her time (6.4), unless another booking was confirmed for it first; then they're
    cancelled and refunded (Reuben, 2026-11-18). Bookings already started are left to
    `cancel_unverified`. The caller commits."""
    waiting = db.scalars(
        select(Booking)
        .where(
            Booking.parent_id == parent_id,
            Booking.status == BookingStatus.awaiting_verification,
            Booking.starts_at > now,
        )
        .order_by(Booking.starts_at)
        .with_for_update()
    ).all()
    confirmed: list[uuid.UUID] = []
    lost: list[uuid.UUID] = []
    cancelled: list[uuid.UUID] = []
    for booking in waiting:
        if booking.id in cancelled or not children_verified(db, booking.id):
            continue
        if slot_taken(db, booking):
            _cancel(
                db,
                [booking],
                BookingStatus.cancelled_slot_taken,
                {"taken_by": str(_holder(db, booking))},
            )
            db.refresh(booking)
            lost.append(booking.id)
            continue
        audit.record(
            db,
            admin_id,
            "booking_confirmed",
            "booking",
            str(booking.id),
            before={"status": booking.status.value},
            after={"status": BookingStatus.confirmed.value, "reason": "children_verified"},
        )
        booking.status = BookingStatus.confirmed
        db.flush()
        confirmed.append(booking.id)
        cancelled.extend(cancel_overlapping(db, booking))
    return AfterVerification(confirmed, lost, cancelled)


def _holder(db: Session, booking: Booking) -> uuid.UUID | None:
    """The booking that holds her time over this one's."""
    return db.scalar(
        select(Booking.id).where(
            Booking.sitter_id == booking.sitter_id,
            Booking.id != booking.id,
            Booking.status.in_(HOLDS_TIME),
            Booking.starts_at < booking.ends_at,
            Booking.ends_at > booking.starts_at,
        )
    )
