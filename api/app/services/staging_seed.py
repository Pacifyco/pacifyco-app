"""Fake people and bookings for **staging**, so it looks lived-in for Reuben's manual pass and the beta (phase
14; Reuben, 2026-11-26). Never for production: the CLI refuses when ENVIRONMENT is production.

    python -m app.cli seed-staging [--parent-email ...] [--sitter-email ...] [--yes] [--replace | --remove]

What it adds:
- 12 live sitters (4 at each level) with weekly hours, ratings and reviews, and 8 verified families with
  1-3 children. Display only: they have no Supabase sign-in, so nobody can sign in as them. Seeding writes
  rows directly, so it emails nobody, and later emails to them are skipped too: their addresses are
  `seed-...@example.com` (reserved, see `email.UNDELIVERABLE`), which is also how they're found again. No
  photos: cards show initials.
- About 27 bookings between them: finished (paid, reviewed, sitter paid), upcoming, waiting for payment,
  a payment to check, requests, one under way, cancellations with refunds (one late, with a strike), an
  overtime charge still owed, sitter pay due, a few chats and an open complaint.
- With Reuben's own test accounts (their emails given on the command line, in his own terminal): a booking
  between them today, so he can check in and out with real codes, plus bookings with seeded people to
  pay, cancel, review, accept and be paid for.

Rows are written as the database owner, like `staging_reset.py`. Each booking gets a `staging_seeded`
audit row, so `--remove` (and `--replace`) can find the ones between Reuben's own accounts too.
"""

import random
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Booking,
    BookingChild,
    BookingHomeInfo,
    BookingStatus,
    Child,
    Complaint,
    ComplaintStatus,
    ComplaintType,
    Consent,
    EarningKind,
    EarningStatus,
    EmergencyContact,
    LegalAcceptance,
    Message,
    OnboardingStatus,
    OnboardingStep,
    OnboardingStepName,
    OvertimeCharge,
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
    Strike,
    StrikeReason,
    VerificationStatus,
    WeeklyHours,
)
from app.services import audit, consent, legal, pricing, sitter_pay, staging_reset
from app.services.availability import INDIA, today_in_india
from app.services.earnings import PAYOUT_WINDOW

EMAIL_PREFIX = "seed-"
EMAIL_DOMAIN = "@example.com"
SEEDED_ACTION = "staging_seeded"

# Approximate centres of the launch pin codes (CLAUDE.md 1), so distances and sorting look right.
POSITIONS = {
    "560001": (12.9766, 77.5993),
    "560034": (12.9352, 77.6245),
    "560038": (12.9783, 77.6408),
    "560078": (12.9063, 77.5857),
    "560084": (13.0125, 77.6277),
    "560095": (12.9345, 77.6266),
    "560103": (12.9256, 77.6761),
}
AREAS = {
    "560001": "MG Road",
    "560034": "Koramangala",
    "560038": "Indiranagar",
    "560078": "JP Nagar",
    "560084": "St Thomas Town",
    "560095": "Koramangala 6th Block",
    "560103": "Bellandur",
}

P, U, R = SitterLevel.pause, SitterLevel.unwind, SitterLevel.recharge
ALL_AGES = ["Toddler", "Preschool", "School age"]


@dataclass(frozen=True)
class FakeSitter:
    name: str
    level: SitterLevel
    pin_code: str
    years: int
    languages: list[str]
    first_aid: bool
    university: str
    semester: int
    ages: list[str]
    bio: str


SITTERS = [
    FakeSitter(
        "Ananya Rao",
        P,
        "560034",
        1,
        ["English", "Kannada"],
        True,
        "Christ University",
        3,
        ["Toddler", "Preschool"],
        "I grew up with four cousins at home, so stories and puzzles are my thing.",
    ),
    FakeSitter(
        "Divya Menon",
        P,
        "560038",
        0,
        ["English", "Malayalam"],
        False,
        "Mount Carmel College",
        2,
        ["Preschool"],
        "Psychology student who loves drawing and simple science experiments with kids.",
    ),
    FakeSitter(
        "Sneha Kulkarni",
        P,
        "560078",
        1,
        ["English", "Hindi"],
        True,
        "Jyoti Nivas College",
        5,
        ["Toddler"],
        "Calm and patient. I help out at my aunt's playschool on Saturdays.",
    ),
    FakeSitter(
        "Priya Shetty",
        P,
        "560095",
        0,
        ["English", "Kannada"],
        False,
        "St. Joseph's University",
        1,
        ["Preschool", "School age"],
        "I love board games, reading aloud and getting homework done on time.",
    ),
    FakeSitter(
        "Kavya Iyer",
        U,
        "560001",
        2,
        ["English", "Tamil"],
        True,
        "Bangalore University",
        6,
        ALL_AGES,
        "Two years of after-school care for neighbours' kids. Bath and bedtime routines are easy.",
    ),
    FakeSitter(
        "Meghana Reddy",
        U,
        "560103",
        2,
        ["English", "Telugu"],
        True,
        "Christ University",
        7,
        ["Preschool", "School age"],
        "Trained classical dancer; I keep kids busy with music and movement.",
    ),
    FakeSitter(
        "Aishwarya Nair",
        U,
        "560034",
        3,
        ["English", "Malayalam", "Hindi"],
        False,
        "Mount Carmel College",
        6,
        ["Toddler", "Preschool"],
        "Big sister to twins. I'm good with toddlers and picky eaters.",
    ),
    FakeSitter(
        "Ritika Sharma",
        U,
        "560084",
        2,
        ["English", "Hindi"],
        True,
        "Jain University",
        4,
        ["School age"],
        "Maths tutor for primary school kids, and a big fan of craft projects.",
    ),
    FakeSitter(
        "Lakshmi Krishnan",
        R,
        "560038",
        4,
        ["English", "Tamil", "Kannada"],
        True,
        "St. Joseph's University",
        8,
        ALL_AGES,
        "Four years with three families. Happy with outings, bath time and evenings.",
    ),
    FakeSitter(
        "Shruthi Gowda",
        R,
        "560078",
        5,
        ["English", "Kannada"],
        True,
        "Bangalore University",
        9,
        ALL_AGES,
        "Early-childhood education student. I plan simple activities for every age.",
    ),
    FakeSitter(
        "Nikita Fernandes",
        R,
        "560001",
        3,
        ["English", "Hindi", "Kannada"],
        True,
        "Christ University",
        8,
        ["Preschool", "School age"],
        "Swimmer and first-aid trained. Park outings are my favourite.",
    ),
    FakeSitter(
        "Farah Siddiqui",
        R,
        "560103",
        4,
        ["English", "Hindi"],
        False,
        "Jain University",
        10,
        ["Toddler", "Preschool"],
        "Final-year student, four years of babysitting, calm with little ones.",
    ),
]


@dataclass(frozen=True)
class FakeChild:
    name: str
    age_years: int
    allergies: str | None = None
    medical_notes: str | None = None
    routines: str | None = None


@dataclass(frozen=True)
class FakeFamily:
    name: str
    relationship: str
    pin_code: str
    street: str
    children: list[FakeChild]
    contact: tuple[str, str]  # name, relationship


FAMILIES = [
    FakeFamily(
        "Rohan Mehta",
        "Father",
        "560034",
        "14, 5th Cross, 1st Block",
        [FakeChild("Aarav", 4, routines="Nap 1-2 pm. Likes a story before sleeping.")],
        ("Sunita Mehta", "Grandmother"),
    ),
    FakeFamily(
        "Neha Kapoor",
        "Mother",
        "560038",
        "221, 12th Main, HAL 2nd Stage",
        [FakeChild("Isha", 6), FakeChild("Kabir", 3, routines="Dinner at 7, bed by 8:30.")],
        ("Rahul Kapoor", "Husband"),
    ),
    FakeFamily(
        "Arjun Pillai",
        "Father",
        "560001",
        "7, Museum Road",
        [FakeChild("Diya", 5, medical_notes="Mild asthma: inhaler in the kitchen drawer, 2 puffs if wheezy.")],
        ("Latha Pillai", "Mother"),
    ),
    FakeFamily(
        "Sana Khan",
        "Mother",
        "560103",
        "B-402, Lake View Apartments",
        [FakeChild("Zara", 2, allergies="Peanuts"), FakeChild("Ayaan", 7)],
        ("Imran Khan", "Husband"),
    ),
    FakeFamily(
        "Vikram Joshi",
        "Father",
        "560078",
        "33, 24th Main, 6th Phase",
        [FakeChild("Myra", 3, routines="Milk at 8 pm.")],
        ("Pallavi Joshi", "Wife"),
    ),
    FakeFamily(
        "Anjali Das",
        "Mother",
        "560095",
        "18, 80 Feet Road",
        [FakeChild("Riya", 8), FakeChild("Dev", 5), FakeChild("Tara", 2, allergies="Dairy")],
        ("Subhash Das", "Father"),
    ),
    FakeFamily(
        "Karthik Subramanian", "Father", "560084", "5, Hennur Main Road", [FakeChild("Aditi", 4)], ("Revathi S", "Wife")
    ),
    FakeFamily(
        "Meera Bhat",
        "Mother",
        "560034",
        "102, 8th Block, 80 Feet Road",
        [FakeChild("Vihaan", 6, routines="Homework first, then 30 minutes of screen time.")],
        ("Ganesh Bhat", "Husband"),
    ),
]


class SeedError(Exception):
    """Something the person running it has to fix first (a readable message, no traceback)."""


@dataclass
class Summary:
    sitters: int = 0
    families: int = 0
    children: int = 0
    bookings: int = 0
    test_bookings: int = 0
    notes: list[str] = field(default_factory=list)


def seeded_ids(db: Session) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(Profile.id).where(Profile.email.like(f"{EMAIL_PREFIX}%{EMAIL_DOMAIN}"), Profile.role != Role.admin)
        )
    )


def seeded_bookings(db: Session) -> list[uuid.UUID]:
    rows = db.scalars(select(AuditLog.entity_id).where(AuditLog.action == SEEDED_ACTION, AuditLog.entity == "booking"))
    return [uuid.UUID(row) for row in rows]


def remove(db: Session) -> staging_reset.Found:
    """Removes everything the seed added: its people, and every booking it made (with their payments,
    earnings, reviews and the rest), including the ones between Reuben's own test accounts."""
    found = staging_reset.find(db, only=seeded_ids(db))
    staging_reset.delete_all(db, found, also_bookings=seeded_bookings(db))
    return found


class _Seeder:
    def __init__(self, db: Session, now: datetime, admin: Profile):
        self.db = db
        self.now = now
        self.admin = admin
        self.today = today_in_india(now)
        self.hour = now.astimezone(INDIA).replace(minute=0, second=0, microsecond=0)
        self.random = random.SystemRandom()
        self.summary = Summary()
        self.sitters: list[tuple[Profile, Sitter]] = []
        self.families: list[tuple[Profile, list[Child]]] = []
        self.paid_earnings: dict[uuid.UUID, list[SitterEarning]] = {}
        self.documents = legal.current_documents(db)

    # ---------- helpers ----------

    def at(self, days: int, hour: int) -> datetime:
        return datetime.combine(self.today + timedelta(days=days), time(hour), INDIA)

    def upi_reference(self) -> str:
        return "".join(self.random.choice("0123456789") for _ in range(12))

    def accept_terms(self, profile: Profile, role: Role, when: datetime) -> None:
        for kind in legal.REQUIRED[role]:
            document = self.documents[kind]
            self.db.add(LegalAcceptance(profile_id=profile.id, document_id=document.id, accepted_at=when))

    def person(self, index: int, name: str, role: Role, pin_code: str, address: str, joined: datetime) -> Profile:
        lat, lng = POSITIONS[pin_code]
        wobble = ((index * 37) % 17 - 8) / 1000  # a few hundred metres, so people aren't on one spot
        profile = Profile(
            id=uuid.uuid4(),
            role=role,
            full_name=name,
            phone=f"+9190000{1 if role == Role.sitter else 2}{index:04d}",
            email=f"{EMAIL_PREFIX}{name.lower().replace(' ', '.')}{EMAIL_DOMAIN}",
            status=ProfileStatus.active,
            pin_code=pin_code,
            address=f"{address}, {AREAS[pin_code]}, Bengaluru",
            lat=Decimal(f"{lat + wobble:.6f}"),
            lng=Decimal(f"{lng - wobble:.6f}"),
            created_at=joined,
        )
        self.db.add(profile)
        self.db.flush()
        return profile

    # ---------- people ----------

    def add_sitters(self) -> None:
        for index, fake in enumerate(SITTERS, start=1):
            joined = self.now - timedelta(days=40 + index)
            profile = self.person(index, fake.name, Role.sitter, fake.pin_code, f"{index * 3}, College Road", joined)
            sitter = Sitter(
                profile_id=profile.id,
                date_of_birth=date(self.today.year - 19 - fake.semester // 3, 1 + index % 12, 1 + index),
                health_disclosure_confirmed_at=joined,
                references_confirmed_at=joined,
                payout_method=PayoutMethod.upi,
                upi_id=f"{EMAIL_PREFIX}{fake.name.split()[0].lower()}@upi",
                bio=fake.bio,
                years_experience=fake.years,
                university=fake.university,
                semester=fake.semester,
                age_groups=fake.ages,
                languages=fake.languages,
                first_aid=fake.first_aid,
                onboarding_status=OnboardingStatus.approved,
                level=fake.level,
            )
            self.db.add(sitter)
            self.db.flush()
            for step in OnboardingStepName:
                self.db.add(
                    OnboardingStep(
                        sitter_id=profile.id,
                        step=step,
                        status=VerificationStatus.approved,
                        reviewed_by=self.admin.id,
                        reviewed_at=joined + timedelta(days=2),
                    )
                )
            self.accept_terms(profile, Role.sitter, joined)
            # Her usual week (6.4): the app's own slots, one weekday off each.
            ends = (13, 16, 19, 22, 24) if fake.level == R else (13, 16, 19, 22)
            for weekday in range(7):
                if weekday == index % 7:
                    continue
                start = 9
                for end in ends:
                    self.db.add(WeeklyHours(sitter_id=profile.id, weekday=weekday, start_hour=start, end_hour=end))
                    start = end
            self.sitters.append((profile, sitter))
        self.summary.sitters = len(SITTERS)

    def add_families(self) -> None:
        for index, fake in enumerate(FAMILIES, start=1):
            joined = self.now - timedelta(days=30 + index)
            profile = self.person(index, fake.name, Role.parent, fake.pin_code, fake.street, joined)
            profile.relationship_to_child = fake.relationship
            self.db.add(Parent(profile_id=profile.id, verification_status=VerificationStatus.approved))
            self.db.flush()
            for kind in consent.REQUIRED_KINDS:
                version = consent.CONSENT_VERSION
                self.db.add(Consent(parent_id=profile.id, kind=kind, version=version, created_at=joined))
            self.accept_terms(profile, Role.parent, joined)
            children = []
            for fake_child in fake.children:
                born = date(self.today.year - fake_child.age_years, self.today.month, min(self.today.day, 28))
                child = Child(
                    parent_id=profile.id,
                    name=fake_child.name,
                    date_of_birth=born - timedelta(days=40),
                    allergies=fake_child.allergies,
                    medical_notes=fake_child.medical_notes,
                    routines=fake_child.routines,
                    verification_status=VerificationStatus.approved,
                    verified_by=self.admin.id,
                    verified_at=joined + timedelta(days=1),
                )
                self.db.add(child)
                children.append(child)
            contact_name, relationship = fake.contact
            self.db.add(
                EmergencyContact(
                    parent_id=profile.id, name=contact_name, relationship=relationship, phone=f"+91900003{index:04d}"
                )
            )
            self.db.flush()
            self.families.append((profile, children))
            self.summary.children += len(children)
        self.summary.families = len(FAMILIES)

    # ---------- bookings ----------

    def booking(
        self,
        parent: Profile,
        children: list[Child],
        sitter: tuple[Profile, Sitter],
        starts_at: datetime,
        units: int,
        status: BookingStatus,
        *,
        paid: bool = True,
        bath_time: bool = False,
        cameras: str | None = None,
        outing: str | None = None,
    ) -> Booking:
        """A booking in this state, with the payment a booking in that state would have."""
        sitter_profile, sitter_row = sitter
        plan = sitter_row.level
        assert plan is not None
        created = min(starts_at - timedelta(days=2), self.now - timedelta(hours=2))
        row = Booking(
            parent_id=parent.id,
            sitter_id=sitter_profile.id,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=units),
            plan=plan,
            units=units,
            children_count=len(children),
            price_paise=pricing.booking_price_paise(plan, len(children), units),
            bath_time=bath_time and plan != SitterLevel.pause,
            status=status,
            # A request she can see now, so her 5 hours to answer (6.4) have only just started.
            request_visible_at=self.now - timedelta(minutes=10) if status == BookingStatus.requested else created,
            created_at=created,
        )
        self.db.add(row)
        self.db.flush()
        for child in children:
            self.db.add(BookingChild(booking_id=row.id, child_id=child.id))
        self.db.add(
            BookingHomeInfo(
                booking_id=row.id, cameras_on=cameras is not None, camera_locations=cameras, outing_where=outing
            )
        )
        if paid:
            self.db.add(
                Payment(
                    booking_id=row.id,
                    parent_id=parent.id,
                    kind=PaymentKind.booking,
                    amount_paise=row.price_paise,
                    status=PaymentStatus.confirmed,
                    upi_reference=self.upi_reference(),
                    confirmed_by=self.admin.id,
                    confirmed_at=created + timedelta(minutes=40),
                    created_at=created + timedelta(minutes=20),
                )
            )
        audit.record(self.db, None, SEEDED_ACTION, "booking", str(row.id), after={"status": status.value})
        self.summary.bookings += 1
        return row

    def finish(self, row: Booking, *, late_minutes: int = 0, paid_out: bool = True) -> None:
        """Checked in at the start and out at the end (plus any overtime); her pay recorded, and paid unless
        it's recent."""
        row.checked_in_at = row.starts_at + timedelta(minutes=3)
        row.checked_out_at = row.ends_at + timedelta(minutes=late_minutes)
        pay = sitter_pay.booking_pay_paise(row.plan, row.units)
        earnings = [self.earning(row, EarningKind.booking, pay, row.units * 60, paid_out)]
        if late_minutes:
            hours = -(-late_minutes // 60)
            charge = OvertimeCharge(
                booking_id=row.id,
                minutes_over=late_minutes,
                hours_charged=hours,
                amount_paise=pricing.hourly_price_paise(row.plan, row.children_count) * hours,
                sitter_pay_paise=sitter_pay.booking_pay_paise(row.plan, hours),
                created_at=row.checked_out_at,
            )
            self.db.add(charge)
            # Still owed: the parent has 2 hours to pay it (6.8).
            self.db.add(
                Payment(
                    booking_id=row.id,
                    parent_id=row.parent_id,
                    kind=PaymentKind.overtime,
                    amount_paise=charge.amount_paise,
                    due_by=row.checked_out_at + timedelta(hours=2),
                    created_at=row.checked_out_at,
                )
            )
            earnings.append(self.earning(row, EarningKind.overtime, charge.sitter_pay_paise, hours * 60, paid_out))
        if paid_out:
            self.paid_earnings.setdefault(row.sitter_id, []).extend(earnings)

    def earning(self, row: Booking, kind: EarningKind, amount: int, minutes: int, paid_out: bool) -> SitterEarning:
        assert row.checked_out_at is not None
        earning = SitterEarning(
            sitter_id=row.sitter_id,
            booking_id=row.id,
            kind=kind,
            amount_paise=amount,
            minutes=minutes,
            status=EarningStatus.released,  # paid ones are moved on when their payout is added
            released_at=row.checked_out_at,
            due_by=row.checked_out_at + PAYOUT_WINDOW,
            created_at=row.checked_out_at,
        )
        self.db.add(earning)
        return earning

    def review(self, row: Booking, author: uuid.UUID, subject: uuid.UUID, rating: int, body: str) -> None:
        assert row.checked_out_at is not None
        self.db.add(
            Review(
                booking_id=row.id,
                author_id=author,
                subject_id=subject,
                rating=rating,
                body=body,
                created_at=row.checked_out_at + timedelta(hours=5),
            )
        )

    def refund(self, row: Booking, when: datetime) -> None:
        self.db.add(
            Payment(
                booking_id=row.id,
                parent_id=row.parent_id,
                kind=PaymentKind.refund,
                amount_paise=-row.price_paise,
                status=PaymentStatus.confirmed,
                transfer_reference=f"SEEDREFUND{self.upi_reference()}",
                confirmed_by=self.admin.id,
                confirmed_at=when + timedelta(hours=3),
                created_at=when,
            )
        )

    def chat(self, parent: Profile, sitter: Profile, start: datetime, lines: list[tuple[str, str]]) -> None:
        for minutes, (who, body) in enumerate(lines):
            sender = parent if who == "parent" else sitter
            self.db.add(
                Message(
                    parent_id=parent.id,
                    sitter_id=sitter.id,
                    sender_id=sender.id,
                    body=body,
                    created_at=start + timedelta(minutes=7 * minutes),
                )
            )

    def add_bookings(self) -> None:
        s = self.sitters
        f = self.families

        def fam(number: int, kids: int = 1) -> tuple[Profile, list[Child]]:
            profile, children = f[number - 1]
            return profile, children[:kids]

        done = BookingStatus.completed
        # Finished, paid, reviewed and her pay sent.
        finished = [
            # family, children, sitter, days ago, hour, hours, rating, review
            (1, 1, 1, -12, 10, 3, 5, "Aarav didn't want her to leave. Lovely with him."),
            (3, 1, 1, -6, 14, 2, 4, "On time and kind. Diya enjoyed the drawing games."),
            (2, 2, 5, -10, 16, 3, 5, "Handled bath and bedtime for both kids without a fuss."),
            (4, 2, 6, -8, 17, 3, 4, "Good with both. A little quiet at first, warmed up quickly."),
            (6, 3, 9, -9, 18, 4, 5, "Three kids, one evening, zero chaos. We'll book her again."),
            (7, 1, 10, -5, 19, 3, 5, "Aditi talks about her every day now."),
            (8, 1, 7, -4, 10, 2, 3, "Fine overall, homework didn't get done though."),
            (5, 1, 3, -11, 9, 3, 5, "Very calm with Myra. Sent us photos and updates."),
            (2, 1, 9, -3, 18, 3, 4, "Reliable and organised."),
            (1, 1, 5, -2, 16, 2, 5, "Great again. Aarav finished his puzzle with her."),
            (6, 2, 11, -7, 19, 3, 4, "The park outing was a hit."),
        ]
        for family, kids, sitter, days, hour, hours, rating, body in finished:
            parent, children = fam(family, kids)
            row = self.booking(parent, children, s[sitter - 1], self.at(days, hour), hours, done)
            self.finish(row)
            self.review(row, parent.id, row.sitter_id, rating, body)
            if family in (1, 2, 6):
                self.review(row, row.sitter_id, parent.id, 5, "Warm family, clear instructions, home on time.")

        # Recent: her pay is due (the admin's payouts list), one with overtime the parent still owes.
        parent, children = fam(3)
        overtime = self.booking(parent, children, s[9], self.hour - timedelta(hours=4), 3, done)
        self.finish(overtime, late_minutes=40, paid_out=False)
        parent, children = fam(4)
        recent = self.booking(parent, children, s[11], self.hour - timedelta(hours=6), 2, done)
        self.finish(recent, paid_out=False)

        # Upcoming and paid.
        parent, children = fam(1)
        self.booking(parent, children, s[1], self.at(1, 10), 2, BookingStatus.confirmed)
        self.chat(
            parent,
            s[1][0],
            self.now - timedelta(hours=20),
            [
                ("parent", "Hi Divya! Aarav naps around 1, so mornings work best."),
                ("sitter", "Hi! 10 o'clock is perfect. Does he have any favourite books?"),
                ("parent", "Anything with dinosaurs."),
            ],
        )
        parent, children = fam(2, 2)
        self.booking(parent, children, s[5], self.at(2, 17), 3, BookingStatus.confirmed, bath_time=True)
        self.chat(
            parent,
            s[5][0],
            self.now - timedelta(hours=30),
            [
                ("sitter", "Hello! Should Kabir have his bath before or after dinner?"),
                ("parent", "After dinner, around 7:30. Towels are in the hall cupboard."),
            ],
        )
        parent, children = fam(6, 3)
        self.booking(
            parent,
            children,
            s[8],
            self.at(3, 16),
            4,
            BookingStatus.confirmed,
            outing="Cubbon Park, by the bandstand",
        )
        self.chat(
            parent,
            s[8][0],
            self.now - timedelta(hours=8),
            [
                ("parent", "We'll be at Cubbon Park that evening. Can you meet us at the bandstand at 4?"),
                ("sitter", "Yes, see you there!"),
            ],
        )
        parent, children = fam(7)
        self.booking(parent, children, s[4], self.at(5, 16), 3, BookingStatus.confirmed)
        parent, children = fam(8)
        self.booking(parent, children, s[10], self.at(4, 19), 3, BookingStatus.confirmed, cameras="Living room")
        parent, children = fam(5)
        self.booking(parent, children, s[3], self.at(6, 9), 3, BookingStatus.confirmed)

        # Accepted, waiting for the parent to pay.
        parent, children = fam(3)
        self.booking(parent, children, s[6], self.at(2, 15), 2, BookingStatus.pending_payment, paid=False)
        # A UPI reference sent, waiting for an admin to check it, and a complaint about it.
        parent, children = fam(4, 2)
        checking = self.booking(parent, children, s[7], self.at(3, 16), 2, BookingStatus.pending_payment, paid=False)
        self.db.add(
            Payment(
                booking_id=checking.id,
                parent_id=parent.id,
                kind=PaymentKind.booking,
                amount_paise=checking.price_paise,
                upi_reference=self.upi_reference(),
                created_at=self.now - timedelta(hours=5),
            )
        )
        raised = self.now - timedelta(hours=3)
        self.db.add(
            Complaint(
                raised_by=parent.id,
                booking_id=checking.id,
                type=ComplaintType.payment,
                description="I paid by UPI this morning and sent the reference, but the booking still says it's "
                "being checked. Can someone confirm?",
                status=ComplaintStatus.open,
                happened_on=self.today,
                reply_by=raised + timedelta(hours=24),
                resolve_by=raised + timedelta(hours=48),
                created_at=raised,
            )
        )

        # Requests for the sitter to answer, and one she declined.
        parent, children = fam(5)
        self.booking(parent, children, s[0], self.at(2, 11), 2, BookingStatus.requested, paid=False)
        parent, children = fam(8)
        self.booking(parent, children, s[11], self.at(4, 10), 3, BookingStatus.requested, paid=False)
        parent, children = fam(7)
        self.booking(parent, children, s[1], self.at(1, 14), 2, BookingStatus.request_declined, paid=False)

        # Under way now.
        parent, children = fam(7)
        under_way = self.booking(parent, children, s[10], self.hour - timedelta(hours=1), 3, BookingStatus.in_progress)
        under_way.checked_in_at = under_way.starts_at + timedelta(minutes=4)

        # Cancelled: by the parent in time (refunded), and by the sitter late (refunded, a strike for her).
        parent, children = fam(1)
        cancelled = self.booking(parent, children, s[2], self.at(-2, 11), 2, BookingStatus.cancelled_parent)
        self.refund(cancelled, self.at(-3, 9))
        parent, children = fam(6, 2)
        late = self.booking(parent, children, s[7], self.at(-5, 17), 3, BookingStatus.cancelled_sitter_late)
        when = late.starts_at - timedelta(hours=4)
        self.refund(late, when)
        self.db.add(
            Strike(
                sitter_id=late.sitter_id,
                booking_id=late.id,
                reason=StrikeReason.late_cancellation,
                given_at=when,
                expires_at=when + timedelta(days=182),
            )
        )
        s[7][1].blocked_until = when + timedelta(hours=24)  # a 1st strike blocks for 24 hours (6.6), long over

    def add_payouts(self) -> None:
        for sitter_id, earnings in self.paid_earnings.items():
            self.db.flush()
            paid_at = min(self.now - timedelta(hours=1), max(e.released_at for e in earnings) + timedelta(hours=3))
            payout = Payout(
                sitter_id=sitter_id,
                amount_paise=sum(e.amount_paise for e in earnings),
                method=PayoutMethod.upi,
                transfer_reference=f"SEEDPAY{self.upi_reference()}",
                paid_by=self.admin.id,
                paid_at=paid_at,
            )
            self.db.add(payout)
            self.db.flush()
            for earning in earnings:
                earning.status = EarningStatus.paid
                earning.payout_id = payout.id

    def update_ratings(self) -> None:
        self.db.flush()
        for profile, sitter in self.sitters:
            ratings = list(self.db.scalars(select(Review.rating).where(Review.subject_id == profile.id)))
            sitter.review_count = len(ratings)
            sitter.avg_rating = (Decimal(sum(ratings)) / len(ratings)).quantize(Decimal("0.01")) if ratings else None

    # ---------- Reuben's own test accounts ----------

    def add_test_bookings(self, parent: Profile | None, sitter: tuple[Profile, Sitter] | None) -> None:
        before = self.summary.bookings
        child = None
        if parent is not None:
            child = self.db.scalar(
                select(Child)
                .where(Child.parent_id == parent.id, Child.verification_status == VerificationStatus.approved)
                .order_by(Child.name)
            )
        if parent is not None and child is not None and sitter is not None:
            # Today, starting this hour: the codes show for this booking, so he can check in and out.
            self.booking(parent, [child], sitter, self.hour, 2, BookingStatus.confirmed)
        if parent is not None and child is not None:
            pause = [item for item in self.sitters if item[1].level == SitterLevel.pause]
            finished = self.booking(parent, [child], pause[0], self.at(-3, 11), 2, BookingStatus.completed)
            self.finish(finished)  # not reviewed yet: he can leave one (14 days)
            self.booking(parent, [child], pause[1], self.at(3, 10), 2, BookingStatus.confirmed)  # to cancel
            self.booking(parent, [child], pause[3], self.at(2, 14), 2, BookingStatus.pending_payment, paid=False)
        if sitter is not None:
            one_child = [(p, c[:1]) for p, c in self.families if len(c) == 1]
            parent_a, kids_a = one_child[0]
            self.booking(parent_a, kids_a, sitter, self.at(2, 15), 2, BookingStatus.requested, paid=False)
            parent_b, kids_b = one_child[3]
            recent = self.booking(parent_b, kids_b, sitter, self.hour - timedelta(hours=4), 2, BookingStatus.completed)
            self.finish(recent, paid_out=False)  # her pay is due: the admin pays it on /admin/payouts
            parent_c, kids_c = one_child[4]
            self.booking(parent_c, kids_c, sitter, self.at(4, 11), 2, BookingStatus.confirmed)
            if sitter[1].payout_method is None:
                self.summary.notes.append(
                    "Your test sitter has no payout details yet, so /admin/payouts can't mark her pay paid until "
                    "she adds them (Payment details)."
                )
        self.summary.test_bookings = self.summary.bookings - before
        self.summary.bookings = before


def _test_parent(db: Session, email: str) -> Profile:
    profile = db.scalar(select(Profile).where(func.lower(Profile.email) == email.lower()))
    if profile is None or profile.role != Role.parent:
        raise SeedError(f"No parent account for {email}. Sign up as a parent with it first.")
    verified = db.scalar(
        select(func.count()).where(
            Child.parent_id == profile.id, Child.verification_status == VerificationStatus.approved
        )
    )
    if not verified:
        raise SeedError(f"{email} has no verified child yet. Add one and approve its birth certificate as admin.")
    return profile


def _test_sitter(db: Session, email: str) -> tuple[Profile, Sitter]:
    found = db.execute(
        select(Profile, Sitter)
        .join(Sitter, Sitter.profile_id == Profile.id)
        .where(func.lower(Profile.email) == email.lower())
    ).first()
    if found is None:
        raise SeedError(f"No sitter account for {email}. Sign up as a sitter with it first.")
    profile, sitter = found
    live = (
        profile.status == ProfileStatus.active
        and sitter.onboarding_status == OnboardingStatus.approved
        and sitter.level is not None
    )
    if not live:
        raise SeedError(f"{email} isn't a live sitter yet. Approve her application and set her level as admin.")
    return profile, sitter


def seed(db: Session, now: datetime, parent_email: str | None = None, sitter_email: str | None = None) -> Summary:
    """Adds the fake people and bookings in one transaction. Refuses if seeded people are already there."""
    if seeded_ids(db):
        raise SeedError("Staging is already seeded. Use --replace to start again, or --remove.")
    admin = db.scalar(select(Profile).where(Profile.role == Role.admin).order_by(Profile.created_at))
    if admin is None:
        raise SeedError("There's no admin yet. Create one first (python -m app.cli create-admin).")
    parent = _test_parent(db, parent_email) if parent_email else None
    sitter = _test_sitter(db, sitter_email) if sitter_email else None
    seeder = _Seeder(db, now, admin)
    seeder.add_sitters()
    seeder.add_families()
    seeder.add_bookings()
    seeder.add_test_bookings(parent, sitter)
    seeder.add_payouts()
    seeder.update_ratings()
    db.commit()
    return seeder.summary
