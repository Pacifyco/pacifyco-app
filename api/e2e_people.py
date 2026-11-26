"""A ready test parent and test sitter for the end-to-end tests (web/e2e/visit-day.e2e.ts), then the staging seed
with bookings for them, the way Reuben uses it on staging (`app/services/staging_seed.py`). Run from the api
folder, with the end-to-end database in DATABASE_URL:

    python e2e_people.py --parent-id ... --parent-email ... --sitter-id ... --sitter-email ...

The ids are the people's (fake) sign-in ids, so the browser can sign in as them. Only for the local or CI
end-to-end database: it refuses any other.
"""

import argparse
import os
import sys
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import sqlalchemy_url
from app.models import (
    Child,
    Consent,
    EmergencyContact,
    LegalAcceptance,
    OnboardingStatus,
    OnboardingStep,
    OnboardingStepName,
    Parent,
    PayoutMethod,
    Profile,
    ProfileStatus,
    Role,
    Sitter,
    SitterLevel,
    VerificationStatus,
    WeeklyHours,
)
from app.services import consent, legal, staging_seed

PARENT_NAME = "Nisha Varma"
CHILD_NAME = "Mira"
SITTER_NAME = "Rekha Das"


def make_people(db: Session, parent_id: uuid.UUID, parent_email: str, sitter_id: uuid.UUID, sitter_email: str):
    now = datetime.now(UTC)
    documents = legal.current_documents(db)
    parent = Profile(
        id=parent_id,
        role=Role.parent,
        full_name=PARENT_NAME,
        email=parent_email,
        status=ProfileStatus.active,
        phone="+919876500010",
        pin_code="560034",
        address="9, 3rd Cross, Koramangala",
        relationship_to_child="Mother",
    )
    sitter = Profile(
        id=sitter_id,
        role=Role.sitter,
        full_name=SITTER_NAME,
        email=sitter_email,
        status=ProfileStatus.active,
        phone="+919876500011",
        pin_code="560034",
        address="4, 1st Main, Koramangala",
    )
    db.add_all([parent, sitter])
    db.flush()
    db.add(Parent(profile_id=parent.id, verification_status=VerificationStatus.approved))
    db.add(
        Sitter(
            profile_id=sitter.id,
            date_of_birth=date(2004, 5, 1),
            health_disclosure_confirmed_at=now,
            references_confirmed_at=now,
            payout_method=PayoutMethod.upi,
            upi_id="rekha.e2e@upi",
            bio="Second-year student who loves reading aloud.",
            years_experience=1,
            university="Christ University",
            semester=3,
            age_groups=["Toddler", "Preschool"],
            languages=["English"],
            onboarding_status=OnboardingStatus.approved,
            level=SitterLevel.pause,
        )
    )
    db.flush()
    for kind in consent.REQUIRED_KINDS:
        db.add(Consent(parent_id=parent.id, kind=kind, version=consent.CONSENT_VERSION))
    for profile, role in ((parent, Role.parent), (sitter, Role.sitter)):
        for kind in legal.REQUIRED[role]:
            db.add(LegalAcceptance(profile_id=profile.id, document_id=documents[kind].id))
    db.add(
        Child(
            parent_id=parent.id,
            name=CHILD_NAME,
            date_of_birth=date(now.year - 4, 2, 1),
            verification_status=VerificationStatus.approved,
        )
    )
    db.add(EmergencyContact(parent_id=parent.id, name="Asha Varma", relationship="Grandparent", phone="+919876500012"))
    for step in OnboardingStepName:
        db.add(OnboardingStep(sitter_id=sitter.id, step=step, status=VerificationStatus.approved, reviewed_at=now))
    for weekday in range(7):
        db.add(WeeklyHours(sitter_id=sitter.id, weekday=weekday, start_hour=9, end_hour=18))
    db.commit()


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("--parent-id", "--parent-email", "--sitter-id", "--sitter-email"):
        parser.add_argument(name, required=True)
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL", "")
    if "pacifyco_e2e" not in database_url or not ("localhost" in database_url or "127.0.0.1" in database_url):
        print("Refusing: this is only for the local end-to-end database (pacifyco_e2e).", file=sys.stderr)
        return 1
    engine = create_engine(sqlalchemy_url(database_url))
    with Session(engine) as db:
        make_people(db, uuid.UUID(args.parent_id), args.parent_email, uuid.UUID(args.sitter_id), args.sitter_email)
        staging_seed.remove(db)  # a run before this one, when the servers were reused
        summary = staging_seed.seed(db, datetime.now(UTC), args.parent_email, args.sitter_email)
    engine.dispose()
    print(f"Seeded {summary.bookings} bookings, {summary.test_bookings} for the test accounts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
