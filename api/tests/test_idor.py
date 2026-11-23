# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""IDOR (CLAUDE.md 9 "Security testing"; phase 12): nobody can read or change another person's data by
changing an id.

A victim family and sitter have one of everything an id can point at: a confirmed booking, a charge, a child,
an authorised adult, a complaint, a document, an overtime request, a rating flag, a reference and a strike.
Then every parent, sitter and personal endpoint that takes an id is called by a *different*, fully set-up
parent or sitter, with the victim's ids. Each must refuse (403 or 404) and say nothing about the victim. The
sweep reads the real routes, so a new endpoint with an id is covered as soon as it's added.
"""

import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from tests.test_admin_bookings import a_charge
from tests.test_admin_payments import confirm, paid, verify_children  # noqa: F401
from tests.test_bookings import book, child_of, children_of, free_sitter  # noqa: F401  (fixtures)
from tests.test_cancellations import confirmed  # noqa: F401  (fixture)
from tests.test_checklists import CONTACTS
from tests.test_documents import (  # noqa: F401  (fixtures)
    accept_consent,
    add_child,
    admin,
    as_user,
    cleanup_documents,
    client,
    parent,
    request_upload,
    scalar,
    storage,
)
from tests.test_marketplace import finished_parent, make_sitter  # noqa: F401  (fixtures)
from tests.test_payments import booking  # noqa: F401  (fixture)
from tests.test_roles import make_profile, real_routes  # noqa: F401  (fixture)
from tests.test_sign_up import PARENT, auth_for, fill_details, user  # noqa: F401  (fixture)
from tests.test_sitter_bookings import signed_in
from tests.test_verification import reviewer, upload  # noqa: F401  (fixture)

# Open to every parent on purpose: a live sitter's profile and her booking options (CLAUDE.md 6.1, 6.4).
PUBLIC_TO_PARENTS = {"/parent/sitters/{sitter_id}", "/parent/sitters/{sitter_id}/booking-options"}
# No one else's id in the path: a day off is looked up among her own.
OWN_ONLY = {"/sitter/availability/days-off/{day}"}
AREAS = ("/parent/", "/sitter/", "/me/", "/documents/")

# One body that fits every endpoint (extra fields are ignored), so a refusal is never just a 422.
BODY = {
    "kind": "emergency",
    "topic": "other",
    "note": "A note.",
    "rating": 5,
    "body": "Hello.",
    "hours": 1,
    "outing_where": None,
    "upi_reference": "123456789012",
    "name": "Asha",
    "date_of_birth": "2023-01-01",
    "no_child_alone": True,
    "adult_with_child": True,
    "child_with_parent": True,
    "code": "1234",
    "lat": None,
    "lng": None,
    "response": "My response.",
    "reason": "A reason.",
    "document_id": str(uuid.uuid4()),
}


@pytest.fixture
def attacker_parent(client, db_engine, storage):
    """A second parent with a finished profile, so a refusal is about whose data it is, nothing else."""
    who = {"id": uuid.uuid4(), "email": f"attacker-{uuid.uuid4()}@example.com"}
    assert client.post("/me/profile", json=PARENT, headers=auth_for(who)).status_code == 201
    try:
        assert fill_details(client, who).status_code == 200
        accept_consent(client, who)
        upload(client, storage, who, "birth_certificate", add_child(db_engine, who["id"]))
        put = client.put("/parent/emergency-contacts", json={"contacts": CONTACTS}, headers=auth_for(who))
        assert put.status_code == 200
        assert client.get("/parent/bookings", headers=auth_for(who)).status_code == 200
        yield who
    finally:
        cleanup_documents(db_engine, who["id"])


@pytest.fixture
def victims(reviewer, client, db_engine, confirmed, finished_parent):
    """The victim family and sitter, with one of everything an id can point at."""
    parent_id, sitter_id = finished_parent["id"], confirmed["sitter_id"]
    sitter = signed_in(db_engine, sitter_id)
    complaint = client.post(
        "/me/complaints", json={"type": "other", "description": "Private."}, headers=auth_for(finished_parent)
    ).json()["id"]
    document = request_upload(client, finished_parent).json()["document_id"]
    with db_engine.begin() as conn:

        def insert(sql: str, **params) -> str:
            return str(conn.execute(text(sql + " RETURNING id"), params).scalar_one())

        ids = {
            "adult_id": insert(
                "INSERT INTO authorised_adults (parent_id, name, relationship, phone) VALUES (:p, 'Gran', 'Gran', "
                "'9876500000')",
                p=parent_id,
            ),
            "request_id": insert(
                "INSERT INTO overtime_requests (booking_id, requested_hours) VALUES (:b, 1)", b=confirmed["id"]
            ),
            "flag_id": insert(
                "INSERT INTO rating_flags (sitter_id, average, reviews_counted, status, told_at, told_by, reason)"
                " VALUES (:s, 3.0, 5, 'told', now(), :a, 'Low ratings')",
                s=sitter_id,
                a=reviewer,
            ),
            "reference_id": insert(
                'INSERT INTO "references" (sitter_id, name, phone, relationship)'
                " VALUES (:s, 'Ref', '9876500001', 'Teacher')",
                s=sitter_id,
            ),
            "strike_id": insert(
                "INSERT INTO strikes (sitter_id, reason, expires_at) VALUES (:s, 'admin', :e)",
                s=sitter_id,
                e=datetime.now(UTC) + timedelta(days=180),
            ),
        }
    return {
        **ids,
        "booking_id": confirmed["id"],
        "payment_id": str(a_charge(db_engine, confirmed)),
        "child_id": str(scalar(db_engine, "SELECT id FROM children WHERE parent_id = :p LIMIT 1", p=parent_id)),
        "complaint_id": complaint,
        "document_id": document,
        "sitter_id": str(sitter_id),
        "parent_id": str(parent_id),
        "names": ["Meera", sitter["email"], finished_parent["email"]],
    }


def endpoints():
    for route in real_routes():
        if "{" in route.path and route.path.startswith(AREAS) and route.path not in PUBLIC_TO_PARENTS | OWN_ONLY:
            for method in route.methods:
                yield method, route.path


def test_nobody_reaches_anothers_data_by_changing_an_id(client, db_engine, victims, attacker_parent, free_sitter):
    attacker_sitter = free_sitter("unwind")
    assert client.get("/sitter/bookings", headers=auth_for(attacker_sitter)).status_code == 200
    swept, leaks = 0, []
    for method, path in sorted(endpoints()):
        url = re.sub(r"\{(\w+)\}", lambda match: victims[match.group(1)], path)
        who = attacker_sitter if path.startswith("/sitter/") else attacker_parent
        response = client.request(method, url, json=BODY, headers=auth_for(who))
        swept += 1
        if response.status_code not in (403, 404) or any(name in response.text for name in victims["names"]):
            leaks.append(f"{method} {path} -> {response.status_code} {response.text[:120]}")
    assert leaks == [], "\n".join(leaks)
    assert swept > 40  # the sweep saw the real endpoints

    # And nothing changed: the victim's booking, charge, child and complaint are as they were.
    assert scalar(db_engine, "SELECT status FROM bookings WHERE id = :b", b=victims["booking_id"]) == "confirmed"
    assert scalar(db_engine, "SELECT status FROM payments WHERE id = :p", p=victims["payment_id"]) == "pending"
    assert scalar(db_engine, "SELECT count(*) FROM children WHERE id = :c", c=victims["child_id"]) == 1
    messages = "SELECT count(*) FROM complaint_messages WHERE complaint_id = :c"
    assert scalar(db_engine, messages, c=victims["complaint_id"]) == 0


def test_admins_reach_anyones_data_only_through_the_admin_area(client, victims, admin):
    """An admin isn't a parent or sitter, so the personal endpoints refuse them too (403), ids or not."""
    for method, path in sorted(endpoints()):
        url = re.sub(r"\{(\w+)\}", lambda match: victims[match.group(1)], path)
        response = client.request(method, url, json=BODY, headers=as_user(admin))
        assert response.status_code in (403, 404), (method, path, response.status_code)
