"""The staging seed (phase 14, `app/services/staging_seed.py`): fake sitters, families and bookings that obey
the app's own rules, so what Reuben sees on staging is what real use would produce. Run here against the test
database, as the database owner, like the seed itself."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import cli
from app.models import (
    Booking,
    BookingChild,
    BookingStatus,
    Child,
    EarningStatus,
    OnboardingStatus,
    Parent,
    Payment,
    PaymentKind,
    PaymentStatus,
    Payout,
    PayoutMethod,
    Profile,
    ProfileStatus,
    Review,
    Role,
    Sitter,
    SitterEarning,
    SitterLevel,
    VerificationStatus,
)
from app.services import checkin, checklists, pricing, search, staging_reset, staging_seed
from app.services.availability import INDIA, today_in_india
from tests.test_auth import TEST_FIELD_ENCRYPTION_KEY


@pytest.fixture
def db(db_engine):
    with Session(db_engine) as session:
        staging_seed.remove(session)  # anything left over from an earlier failed run
        yield session
        session.rollback()
        staging_seed.remove(session)


@pytest.fixture
def admin(db):
    profile = Profile(id=uuid.uuid4(), role=Role.admin, full_name="Seed Admin", email=f"admin-{uuid.uuid4()}@x.com")
    db.add(profile)
    db.commit()
    yield profile
    db.rollback()
    staging_seed.remove(db)
    db.delete(db.get(Profile, profile.id))
    db.commit()


@pytest.fixture
def test_accounts(db, admin):
    """Reuben's own test parent (one verified child) and live sitter."""
    parent = Profile(
        id=uuid.uuid4(),
        role=Role.parent,
        full_name="Test Parent",
        email=f"parent-{uuid.uuid4()}@x.com",
        status=ProfileStatus.active,
        phone="+919876543210",
        pin_code="560034",
        address="1 Test Road",
        relationship_to_child="Mother",
    )
    sitter = Profile(
        id=uuid.uuid4(),
        role=Role.sitter,
        full_name="Test Sitter",
        email=f"sitter-{uuid.uuid4()}@x.com",
        status=ProfileStatus.active,
        phone="+919876543211",
        pin_code="560034",
        address="2 Test Road",
    )
    db.add_all([parent, sitter])
    db.flush()
    db.add(Parent(profile_id=parent.id, verification_status=VerificationStatus.approved))
    db.add(
        Sitter(
            profile_id=sitter.id,
            onboarding_status=OnboardingStatus.approved,
            level=SitterLevel.pause,
            payout_method=PayoutMethod.upi,
            upi_id="test@upi",
        )
    )
    db.flush()
    db.add(
        Child(
            parent_id=parent.id,
            name="Test Child",
            date_of_birth=date(2021, 1, 1),
            verification_status=VerificationStatus.approved,
        )
    )
    db.commit()
    yield parent, sitter
    db.rollback()
    staging_seed.remove(db)
    staging_reset.delete_all(db, staging_reset.find(db, only=[parent.id, sitter.id]))


def seeded_bookings(db) -> list[Booking]:
    ids = staging_seed.seeded_bookings(db)
    return list(db.scalars(select(Booking).where(Booking.id.in_(ids))))


def test_seeds_live_sitters_and_finished_families(db, admin):
    summary = staging_seed.seed(db, datetime.now(UTC))
    assert (summary.sitters, summary.families) == (12, 8)
    ids = staging_seed.seeded_ids(db)

    live = db.scalars(
        select(Sitter.level).join(Profile, Profile.id == Sitter.profile_id).where(search._live(), Profile.id.in_(ids))
    ).all()
    assert len(live) == 12
    assert {level: live.count(level) for level in SitterLevel} == dict.fromkeys(SitterLevel, 4)

    parents = db.scalars(select(Profile).where(Profile.id.in_(ids), Profile.role == Role.parent)).all()
    assert len(parents) == 8
    for parent in parents:
        items = checklists.parent_checklist(db, parent)
        assert all(item.status in (checklists.ItemStatus.done, checklists.ItemStatus.approved) for item in items)


def test_bookings_follow_the_rules(db, admin):
    staging_seed.seed(db, datetime.now(UTC))
    bookings = seeded_bookings(db)
    assert len(bookings) >= 25
    for row in bookings:
        children = db.scalar(select(func.count()).where(BookingChild.booking_id == row.id))
        assert children == row.children_count
        sitter = db.get(Sitter, row.sitter_id)
        assert row.plan == sitter.level  # a sitter works only her own level's plan (6.2)
        assert row.price_paise == pricing.booking_price_paise(row.plan, row.children_count, row.units)
    statuses = {row.status for row in bookings}
    for wanted in (
        BookingStatus.completed,
        BookingStatus.confirmed,
        BookingStatus.pending_payment,
        BookingStatus.requested,
        BookingStatus.in_progress,
        BookingStatus.cancelled_parent,
        BookingStatus.cancelled_sitter_late,
    ):
        assert wanted in statuses


def test_money_adds_up(db, admin):
    staging_seed.seed(db, datetime.now(UTC))
    ids = staging_seed.seeded_ids(db)
    for payout in db.scalars(select(Payout).where(Payout.sitter_id.in_(ids))):
        paid = db.scalars(select(SitterEarning.amount_paise).where(SitterEarning.payout_id == payout.id)).all()
        assert payout.amount_paise == sum(paid)
    due = db.scalars(
        select(SitterEarning).where(SitterEarning.sitter_id.in_(ids), SitterEarning.status == EarningStatus.released)
    ).all()
    assert due and all(earning.due_by > datetime.now(UTC) - timedelta(hours=8) for earning in due)
    # One overtime charge still owed, and one UPI reference waiting for an admin.
    pending = db.scalars(select(Payment).where(Payment.parent_id.in_(ids), Payment.status == PaymentStatus.pending))
    assert {payment.kind for payment in pending} == {PaymentKind.overtime, PaymentKind.booking}
    # Every refund is the whole price back.
    for refund in db.scalars(select(Payment).where(Payment.parent_id.in_(ids), Payment.kind == PaymentKind.refund)):
        assert refund.amount_paise == -db.get(Booking, refund.booking_id).price_paise


def test_ratings_match_the_reviews(db, admin):
    staging_seed.seed(db, datetime.now(UTC))
    for sitter in db.scalars(select(Sitter).where(Sitter.profile_id.in_(staging_seed.seeded_ids(db)))):
        ratings = db.scalars(select(Review.rating).where(Review.subject_id == sitter.profile_id)).all()
        assert sitter.review_count == len(ratings)
        if ratings:
            assert abs(float(sitter.avg_rating) - sum(ratings) / len(ratings)) < 0.01
        else:
            assert sitter.avg_rating is None


def test_gives_the_test_accounts_a_booking_to_check_in_today(db, test_accounts):
    parent, sitter = test_accounts
    now = datetime.now(UTC)
    summary = staging_seed.seed(db, now, parent.email, sitter.email)
    assert summary.test_bookings == 7
    today = db.scalar(select(Booking).where(Booking.parent_id == parent.id, Booking.sitter_id == sitter.id))
    assert today.status == BookingStatus.confirmed
    assert today.starts_at.astimezone(INDIA).date() == today_in_india(now)
    # The real check-in code shows for it.
    code = checkin.check_in_code(db, parent.id, today.id, TEST_FIELD_ENCRYPTION_KEY, now)
    assert len(code) == 4

    theirs = db.scalars(select(Booking.status).where(Booking.parent_id == parent.id)).all()
    assert sorted(theirs) == sorted(
        [BookingStatus.confirmed, BookingStatus.completed, BookingStatus.confirmed, BookingStatus.pending_payment]
    )
    hers = db.scalars(select(Booking.status).where(Booking.sitter_id == sitter.id)).all()
    assert BookingStatus.requested in hers
    assert db.scalar(
        select(func.count()).where(SitterEarning.sitter_id == sitter.id, SitterEarning.status == EarningStatus.released)
    )


def test_refuses_accounts_that_arent_ready(db, admin, test_accounts):
    parent, sitter = test_accounts
    with pytest.raises(staging_seed.SeedError, match="isn't a live sitter"):
        db.get(Sitter, sitter.id).level = None
        db.flush()
        staging_seed.seed(db, datetime.now(UTC), sitter_email=sitter.email)
    db.rollback()
    with pytest.raises(staging_seed.SeedError, match="No parent account"):
        staging_seed.seed(db, datetime.now(UTC), parent_email=sitter.email)
    db.rollback()
    assert staging_seed.seeded_ids(db) == []


def test_seeds_once_then_replaces_and_removes_cleanly(db, test_accounts):
    parent, sitter = test_accounts
    staging_seed.seed(db, datetime.now(UTC), parent.email, sitter.email)
    with pytest.raises(staging_seed.SeedError, match="already seeded"):
        staging_seed.seed(db, datetime.now(UTC))
    db.rollback()

    staging_seed.remove(db)
    staging_seed.seed(db, datetime.now(UTC), parent.email, sitter.email)
    assert len(staging_seed.seeded_ids(db)) == 20

    staging_seed.remove(db)
    assert staging_seed.seeded_ids(db) == []
    assert staging_seed.seeded_bookings(db) == []
    # Every booking it made is gone, the ones between the test accounts too; the accounts themselves stay.
    mine = select(func.count()).where((Booking.parent_id == parent.id) | (Booking.sitter_id == sitter.id))
    assert db.scalar(mine) == 0
    assert db.get(Profile, parent.id) is not None and db.get(Profile, sitter.id) is not None


def test_the_command_refuses_production(monkeypatch, capsys):
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert cli.seed_staging(None, None, "add", True, "postgresql+psycopg://x@nowhere/db") == 1
    assert "staging only" in capsys.readouterr().err


def test_the_command_says_first_then_seeds_and_removes(db_engine, db, admin, monkeypatch, capsys):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    url = db_engine.url.render_as_string(hide_password=False)
    assert cli.seed_staging(None, None, "add", False, url) == 0
    assert "Would add 12 sitters, 8 families" in capsys.readouterr().out
    assert staging_seed.seeded_ids(db) == []

    assert cli.seed_staging(None, None, "add", True, url) == 0
    out = capsys.readouterr().out
    assert "Added 12 sitters, 8 families" in out and "can't sign in" in out

    assert cli.seed_staging(None, None, "remove", True, url) == 0
    assert "Removed 8 seeded families and 12 seeded sitters" in capsys.readouterr().out
    db.expire_all()
    assert staging_seed.seeded_ids(db) == []
