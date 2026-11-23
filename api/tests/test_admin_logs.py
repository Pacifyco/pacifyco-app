# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""The audit log and the document access log, for admins (phase 10; CLAUDE.md 5).

Read-only views of two append-only logs, newest first, 50 at a time: who did what to which record, and
which admin opened whose document. Admins only.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from tests.test_documents import (  # noqa: F401  (fixtures)
    add_child,
    admin,
    as_user,
    client,
    parent,
    request_upload,
    storage,
)
from tests.test_roles import make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import auth_for, user  # noqa: F401  (fixture)
from tests.test_verification import reviewer  # noqa: F401  (fixture)


def audit_log(client, admin_id, **params):
    response = client.get("/admin/audit-log", params=params, headers=as_user(admin_id))
    assert response.status_code == 200, response.text
    return response.json()


def document_log(client, viewer, **params):
    response = client.get("/admin/document-access-log", params=params, headers=as_user(viewer))
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def audit_rows(db_engine):
    """Adds audit rows as the owner (the API can't write them by hand) and removes them afterwards."""
    added = []

    def add(actor_id, action, entity, entity_id, before=None, after=None):
        with db_engine.begin() as conn:
            added.append(
                conn.execute(
                    text(
                        "INSERT INTO audit_log (actor_id, action, entity, entity_id, before, after)"
                        " VALUES (:a, :action, :e, :id, CAST(:b AS jsonb), CAST(:f AS jsonb)) RETURNING id"
                    ),
                    {
                        "a": actor_id,
                        "action": action,
                        "e": entity,
                        "id": str(entity_id),
                        "b": None if before is None else json.dumps(before),
                        "f": None if after is None else json.dumps(after),
                    },
                ).scalar_one()
            )

    yield add
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM audit_log WHERE id = ANY(:ids)"), {"ids": added})


def name(db_engine, profile_id, full_name):
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE profiles SET full_name = :n WHERE id = :id"), {"n": full_name, "id": profile_id})


# ---------- the audit log ----------


def test_who_did_what_newest_first(client, db_engine, reviewer, parent, audit_rows):
    name(db_engine, reviewer, "Asha Admin")
    name(db_engine, parent["id"], "Priya Rao")
    booking_id = uuid.uuid4()
    audit_rows(reviewer, "sitter_level_set", "sitters", parent["id"], before={"level": None}, after={"level": "pause"})
    audit_rows(None, "booking_cancelled", "booking", booking_id, after={"status": "cancelled_unpaid"})

    about_her = audit_log(client, reviewer, entity="sitters", entity_id=str(parent["id"]))
    assert about_her["more"] is False
    [entry] = about_her["entries"]
    assert entry["by"] == "Asha Admin" and entry["by_id"] == str(reviewer)
    assert entry["action"] == "sitter_level_set"
    assert entry["person"] == {"id": str(parent["id"]), "full_name": "Priya Rao", "role": "parent"}
    assert entry["before"] == {"level": None} and entry["after"] == {"level": "pause"}

    [by_rules] = audit_log(client, reviewer, by="rules", entity_id=str(booking_id))["entries"]
    assert by_rules["by"] is None and by_rules["by_id"] is None and by_rules["person"] is None
    assert audit_log(client, reviewer, by=str(reviewer), entity_id=str(booking_id))["entries"] == []

    mine = audit_log(client, reviewer, by=str(reviewer))["entries"]
    assert [item["action"] for item in mine] == ["sitter_level_set"]
    newest = audit_log(client, reviewer)["entries"]
    assert [item["entity_id"] for item in newest[:2]] == [str(booking_id), str(parent["id"])]


def test_filters_by_words_and_dates(client, reviewer, audit_rows):
    record = uuid.uuid4()
    audit_rows(reviewer, "charge_waived", "payment", record)
    assert len(audit_log(client, reviewer, entity_id=str(record), action="charge waived")["entries"]) == 1
    assert len(audit_log(client, reviewer, entity_id=str(record), action="WAIVED")["entries"]) == 1
    assert audit_log(client, reviewer, entity_id=str(record), action="refund")["entries"] == []
    assert audit_log(client, reviewer, entity_id=str(record), action="%")["entries"] == []  # not a wildcard
    assert audit_log(client, reviewer, entity_id=str(record), entity="booking")["entries"] == []
    today = datetime.now(UTC).astimezone(ZoneInfo("Asia/Kolkata")).date()
    assert len(audit_log(client, reviewer, entity_id=str(record), on_from=today, on_to=today)["entries"]) == 1
    tomorrow = (today + timedelta(days=1)).isoformat()
    assert audit_log(client, reviewer, entity_id=str(record), on_from=tomorrow)["entries"] == []
    yesterday = (today - timedelta(days=1)).isoformat()
    assert audit_log(client, reviewer, entity_id=str(record), on_to=yesterday)["entries"] == []


def test_fifty_at_a_time(client, reviewer, audit_rows):
    record = uuid.uuid4()
    for _ in range(51):
        audit_rows(reviewer, "checked_in", "booking", record)
    first = audit_log(client, reviewer, entity_id=str(record))
    assert len(first["entries"]) == 50 and first["more"] is True
    second = audit_log(client, reviewer, entity_id=str(record), page=1)
    assert len(second["entries"]) == 1 and second["more"] is False
    assert second["entries"][0]["id"] < first["entries"][-1]["id"]


def test_a_made_up_actor_is_refused(client, reviewer):
    response = client.get("/admin/audit-log", params={"by": "someone"}, headers=as_user(reviewer))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_actor"


def test_the_admins_for_the_filters(client, db_engine, reviewer, make_profile):
    name(db_engine, reviewer, "Asha Admin")
    not_an_admin = make_profile("sitter", "active")
    response = client.get("/admin/admins", headers=as_user(reviewer))
    assert response.status_code == 200
    found = {item["id"]: item["full_name"] for item in response.json()}
    assert found[str(reviewer)] == "Asha Admin"
    assert str(not_an_admin) not in found


# ---------- the document access log ----------


def test_who_opened_whose_document(client, db_engine, admin, parent, make_profile):
    name(db_engine, admin, "Asha Admin")
    name(db_engine, parent["id"], "Priya Rao")
    other_admin = make_profile("admin", "active")
    ticket = request_upload(client, parent).json()
    url = f"/admin/documents/{ticket['document_id']}/view-url"
    assert client.get(url, headers=as_user(admin)).status_code == 200
    assert client.get(url, headers=as_user(other_admin)).status_code == 200
    try:
        views = document_log(client, admin, owner_id=str(parent["id"]))
        assert views["more"] is False
        assert [item["admin_id"] for item in views["views"]] == [str(other_admin), str(admin)]  # newest first
        latest, first = views["views"]
        assert first["admin_name"] == "Asha Admin"
        assert first["document_id"] == ticket["document_id"]
        assert first["document_type"] == "government_id"
        assert first["deleted"] is False and first["child_name"] is None
        assert first["owner"] == {"id": str(parent["id"]), "full_name": "Priya Rao", "role": "parent"}

        mine = document_log(client, admin, admin_id=str(admin), owner_id=str(parent["id"]))["views"]
        assert [item["id"] for item in mine] == [first["id"]]
        assert len(document_log(client, admin, owner="priya r")["views"]) >= 2
        assert document_log(client, admin, owner="nobody-by-this-name")["views"] == []
        by_type = document_log(client, admin, owner_id=str(parent["id"]), document_type="police_certificate")
        assert by_type["views"] == []
    finally:
        with db_engine.begin() as conn:
            conn.execute(text("DELETE FROM document_access_log WHERE admin_id = :id"), {"id": other_admin})


def test_a_childs_certificate_since_deleted(client, db_engine, admin, parent):
    child_id = add_child(db_engine, parent["id"])
    document_id = uuid.uuid4()
    with db_engine.begin() as conn:  # as it is once the child is verified: the file deleted, the row kept
        conn.execute(
            text(
                "INSERT INTO documents (id, owner_profile_id, child_id, type, storage_path, status, deleted_at)"
                " VALUES (:id, :p, :c, 'birth_certificate', :path, 'uploaded', now())"
            ),
            {"id": document_id, "p": parent["id"], "c": child_id, "path": f"{parent['id']}/{document_id}"},
        )
        conn.execute(
            text("INSERT INTO document_access_log (document_id, admin_id) VALUES (:d, :a)"),
            {"d": document_id, "a": admin},
        )
    [view] = document_log(client, admin, owner_id=str(parent["id"]), document_type="birth_certificate")["views"]
    assert view["child_name"] == "Asha" and view["deleted"] is True


def test_an_unknown_document_type_is_refused(client, admin):
    response = client.get("/admin/document-access-log", params={"document_type": "aadhaar"}, headers=as_user(admin))
    assert response.status_code == 422


# ---------- admins only ----------


@pytest.mark.parametrize("path", ["/admin/audit-log", "/admin/document-access-log", "/admin/admins"])
def test_admins_only(client, parent, path):
    assert client.get(path, headers=auth_for(parent)).status_code == 403
