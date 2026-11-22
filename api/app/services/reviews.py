"""Reviews both ways, and the low-rating flag (CLAUDE.md 6.11; phase 9).

- Who and when: the booking's parent and its sitter, each once, after a booking where care happened
  (checked out, or closed by an admin after she checked in) and within 14 days of its end (Reuben,
  2026-11-22). A 1-5 rating and an optional short review.
- Who sees what (Reuben, 2026-11-22): parents see a sitter's average, count and written reviews on her
  profile, and she sees them too. Only admins see a sitter's review of a parent.
- A sitter's average and count (`sitters.avg_rating`, `review_count`) are worked out again from every
  review about her whenever one is left.
- The flag: when the average of her last 10 reviews is below 3.5, once she has at least 5 (Reuben,
  2026-11-22), she's flagged for admin review (the admins are emailed). Before any removal for ratings she
  must be told the reason and given a chance to respond (recorded): an admin tells her, she responds, an
  admin closes it with a note. She has 12 hours from being told to respond
  (Reuben, 2026-11-22); after that an admin may decide without it. Removing an account is phase 10 (user management).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Booking, BookingStatus, Profile, RatingFlag, RatingFlagStatus, Review, Role, Sitter
from app.services import audit

WINDOW = timedelta(days=14)
RESPOND_WITHIN = timedelta(hours=12)  # from being told (Reuben, 2026-11-22)
LAST = 10  # her last 10 reviews
FLAG_FROM = 5  # ...once she has at least 5
FLAG_BELOW = Decimal("3.5")
BODY_MAX = 500
PUBLIC_LIMIT = 50  # written reviews shown on her profile, newest first
TWO_PLACES = Decimal("0.01")


def care_happened(booking: Booking) -> bool:
    """Checked out, or closed by an admin after she checked in."""
    return booking.status == BookingStatus.completed or (
        booking.status == BookingStatus.closed_by_admin and booking.checked_in_at is not None
    )


def open_until(booking: Booking) -> datetime:
    """Reviews close 14 days after the booking's end (or its check-out, if later)."""
    end = booking.ends_at
    if booking.checked_out_at is not None and booking.checked_out_at > end:
        end = booking.checked_out_at
    return end + WINDOW


def mine(db: Session, booking_id: uuid.UUID, author_id: uuid.UUID) -> Review | None:
    return db.scalar(select(Review).where(Review.booking_id == booking_id, Review.author_id == author_id))


def can_review(db: Session, booking: Booking, author_id: uuid.UUID, now: datetime) -> bool:
    return care_happened(booking) and now <= open_until(booking) and mine(db, booking.id, author_id) is None


def _clean(text: str | None) -> str | None:
    text = (text or "").strip()
    return text or None


def _round(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass
class Left:
    review: Review
    flag: RatingFlag | None  # a new low-rating flag this review caused


def leave(db: Session, author: Profile, booking_id: uuid.UUID, rating: int, body: str | None, now: datetime) -> Left:
    """The author's review of the other person on this booking. Commits."""
    column = Booking.parent_id if author.role == Role.parent else Booking.sitter_id
    booking = db.scalar(select(Booking).where(Booking.id == booking_id, column == author.id))
    if booking is None:
        raise AppError(404, "not_found", "We couldn't find that booking.")
    if not care_happened(booking):
        raise AppError(409, "not_reviewable", "You can leave a review once a booking has finished.")
    if now > open_until(booking):
        raise AppError(409, "review_closed", "Reviews close 14 days after the booking.")
    if not 1 <= rating <= 5:
        raise AppError(422, "invalid_rating", "Choose from 1 to 5 stars.")
    if mine(db, booking.id, author.id) is not None:
        raise AppError(409, "already_reviewed", "You've already reviewed this booking.")
    about_sitter = author.role == Role.parent
    subject_id = booking.sitter_id if about_sitter else booking.parent_id
    review = Review(booking_id=booking.id, author_id=author.id, subject_id=subject_id, rating=rating, body=_clean(body))
    try:
        with db.begin_nested():
            db.add(review)
            db.flush()
    except IntegrityError:  # left twice at the same moment
        raise AppError(409, "already_reviewed", "You've already reviewed this booking.") from None
    audit.record(
        db,
        author.id,
        "review_left",
        "review",
        str(review.id),
        after={"booking_id": str(booking.id), "about": "sitter" if about_sitter else "parent", "rating": rating},
    )
    flag = None
    if about_sitter:
        refresh_rating(db, booking.sitter_id)
        flag = flag_if_low(db, booking.sitter_id)
    db.commit()
    return Left(review=review, flag=flag)


def refresh_rating(db: Session, sitter_id: uuid.UUID) -> None:
    """Her average and count, from every review about her (shown on her profile, 6.11)."""
    average, count = db.execute(
        select(func.avg(Review.rating), func.count(Review.id)).where(Review.subject_id == sitter_id)
    ).one()
    sitter = db.get(Sitter, sitter_id)
    assert sitter is not None
    sitter.avg_rating = _round(Decimal(average)) if count else None
    sitter.review_count = count


def last_ten(db: Session, sitter_id: uuid.UUID) -> tuple[Decimal | None, int]:
    """The average of her last 10 reviews, and how many that is."""
    ratings = db.scalars(
        select(Review.rating)
        .where(Review.subject_id == sitter_id)
        .order_by(Review.created_at.desc(), Review.id.desc())
        .limit(LAST)
    ).all()
    if not ratings:
        return None, 0
    return _round(Decimal(sum(ratings)) / len(ratings)), len(ratings)


def current_flag(db: Session, sitter_id: uuid.UUID) -> RatingFlag | None:
    """Her flag still in progress (not closed), if any."""
    return db.scalar(
        select(RatingFlag).where(RatingFlag.sitter_id == sitter_id, RatingFlag.status != RatingFlagStatus.closed)
    )


def flag_if_low(db: Session, sitter_id: uuid.UUID) -> RatingFlag | None:
    """Flags her when her last-10 average is below 3.5 (with 5+ reviews) and she isn't flagged already."""
    average, count = last_ten(db, sitter_id)
    if average is None or count < FLAG_FROM or average >= FLAG_BELOW:
        return None
    if current_flag(db, sitter_id) is not None:
        return None
    flag = RatingFlag(sitter_id=sitter_id, average=average, reviews_counted=count)
    db.add(flag)
    db.flush()
    audit.record(
        db,
        None,
        "rating_flagged",
        "rating_flag",
        str(flag.id),
        after={"sitter_id": str(sitter_id), "average": str(average), "reviews_counted": count},
    )
    return flag


def respond_by(flag: RatingFlag) -> datetime | None:
    """When her 12 hours to respond end, once she's been told."""
    return flag.told_at + RESPOND_WITHIN if flag.told_at is not None else None


def can_decide(flag: RatingFlag, now: datetime) -> bool:
    """Whether an admin may decide on her (6.11): she has responded, or her 12 hours have passed."""
    deadline = respond_by(flag)
    return flag.response is not None or (deadline is not None and now >= deadline)


def _flag(db: Session, flag_id: uuid.UUID) -> RatingFlag:
    flag = db.get(RatingFlag, flag_id, with_for_update=True)
    if flag is None:
        raise AppError(404, "not_found", "We couldn't find that flag.")
    return flag


def _state(flag: RatingFlag) -> dict:
    return {"status": flag.status.value}


def tell(db: Session, admin_id: uuid.UUID, flag_id: uuid.UUID, reason: str, now: datetime) -> RatingFlag:
    """An admin tells her why she's been flagged; she can then respond. Commits."""
    reason_text = _clean(reason)
    if reason_text is None:
        raise AppError(422, "reason_required", "Tell her the reason.")
    flag = _flag(db, flag_id)
    if flag.status == RatingFlagStatus.closed:
        raise AppError(409, "flag_closed", "This flag has been closed.")
    if flag.status != RatingFlagStatus.open:
        raise AppError(409, "already_told", "She's already been told.")
    before = _state(flag)
    flag.status = RatingFlagStatus.told
    flag.told_by = admin_id
    flag.told_at = now
    flag.reason = reason_text
    audit.record(db, admin_id, "rating_flag_told", "rating_flag", str(flag.id), before=before, after=_state(flag))
    db.commit()
    return flag


def respond(db: Session, sitter_id: uuid.UUID, flag_id: uuid.UUID, response: str, now: datetime) -> RatingFlag:
    """Her response, recorded (6.11). Commits."""
    response_text = _clean(response)
    if response_text is None:
        raise AppError(422, "response_required", "Write your response.")
    flag = _flag(db, flag_id)
    # Not hers, or not yet told to her: as if it didn't exist.
    if flag.sitter_id != sitter_id or flag.status == RatingFlagStatus.open:
        raise AppError(404, "not_found", "We couldn't find that flag.")
    if flag.status == RatingFlagStatus.closed:
        raise AppError(409, "flag_closed", "This has already been decided.")
    if flag.status == RatingFlagStatus.responded:
        raise AppError(409, "already_responded", "You've already responded.")
    before = _state(flag)
    flag.status = RatingFlagStatus.responded
    flag.response = response_text
    flag.responded_at = now
    audit.record(db, sitter_id, "rating_flag_responded", "rating_flag", str(flag.id), before=before, after=_state(flag))
    db.commit()
    return flag


def close(db: Session, admin_id: uuid.UUID, flag_id: uuid.UUID, note: str, now: datetime) -> RatingFlag:
    """An admin closes the flag with a note (internal): before she's told, or once she has responded or her
    12 hours have passed. Commits."""
    note_text = _clean(note)
    if note_text is None:
        raise AppError(422, "note_required", "Add a note on what you decided.")
    flag = _flag(db, flag_id)
    if flag.status == RatingFlagStatus.closed:
        raise AppError(409, "flag_closed", "This flag has been closed.")
    # Once she's been told, she has 12 hours to respond before anything is decided. A flag she was never
    # told about can be closed at once (no action against her).
    if flag.status == RatingFlagStatus.told and not can_decide(flag, now):
        raise AppError(409, "waiting_for_response", "She has 12 hours from being told to respond.")
    before = _state(flag)
    flag.status = RatingFlagStatus.closed
    flag.closed_by = admin_id
    flag.closed_at = now
    flag.close_note = note_text
    audit.record(db, admin_id, "rating_flag_closed", "rating_flag", str(flag.id), before=before, after=_state(flag))
    db.commit()
    return flag


def open_flags(db: Session) -> list[RatingFlag]:
    """Flags not yet closed, oldest first."""
    return list(
        db.scalars(
            select(RatingFlag).where(RatingFlag.status != RatingFlagStatus.closed).order_by(RatingFlag.created_at)
        )
    )


def her_flag(db: Session, sitter_id: uuid.UUID) -> RatingFlag | None:
    """What she sees: a flag she's been told about and that's still open."""
    flag = current_flag(db, sitter_id)
    return flag if flag is not None and flag.status != RatingFlagStatus.open else None


@dataclass
class Written:
    id: uuid.UUID
    booking_id: uuid.UUID
    rating: int
    body: str | None
    author_name: str | None
    created_at: datetime


def about(db: Session, subject_id: uuid.UUID, limit: int | None = None) -> list[Written]:
    """Reviews about this person, newest first, with the author's full name (callers decide how much of it
    to show)."""
    query = (
        select(Review, Profile.full_name)
        .join(Profile, Profile.id == Review.author_id)
        .where(Review.subject_id == subject_id)
        .order_by(Review.created_at.desc(), Review.id.desc())
    )
    if limit is not None:
        query = query.limit(limit)
    return [
        Written(
            id=review.id,
            booking_id=review.booking_id,
            rating=review.rating,
            body=review.body,
            author_name=name,
            created_at=review.created_at,
        )
        for review, name in db.execute(query)
    ]
