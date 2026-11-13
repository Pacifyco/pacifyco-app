"""Verification documents (CLAUDE.md sections 5, 7 and 9): signed upload URLs, real content/size
checks on confirm (not the filename), ownership (no IDOR), and admin-only, logged viewing."""

import uuid

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import get_key_source
from app.errors import AppError
from app.main import create_app
from app.services import consent
from app.services.documents import MAX_FILE_BYTES, sniff_content_type
from app.services.email import get_email
from app.services.storage import get_storage
from tests.test_auth import FakeKeys, make_settings
from tests.test_migrations import alembic_config
from tests.test_roles import as_user, make_profile  # noqa: F401  (fixture)
from tests.test_sign_up import ACCEPTED, PARENT, auth_for, fill_details, user  # noqa: F401  (fixture)

PDF = b"%PDF-1.4\n%fake but starts right\n"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
NOT_A_DOCUMENT = b"MZ\x90\x00 this is not a pdf, jpg or png"
OVERSIZED_PDF = b"%PDF-1.4\n" + b"0" * MAX_FILE_BYTES


class FakeStorage:
    """Stands in for Supabase Storage. `put` simulates the browser's PUT to the signed upload URL."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def put(self, path: str, data: bytes) -> None:
        self.objects[path] = data

    def create_signed_upload_url(self, path: str) -> str:
        return f"https://fake.storage/upload/{path}?token=test-upload"

    def create_signed_view_url(self, path: str) -> str:
        return f"https://fake.storage/view/{path}?token=test-view"

    def download(self, path: str) -> bytes:
        if path not in self.objects:
            raise AppError(404, "storage_object_not_found", "That file doesn't exist in storage")
        return self.objects[path]

    def delete(self, path: str) -> None:
        self.deleted.append(path)
        self.objects.pop(path, None)


@pytest.fixture
def storage():
    return FakeStorage()


@pytest.fixture
def client(db_engine, storage, mailbox):
    command.upgrade(alembic_config(db_engine), "head")
    app = create_app(make_settings(db_engine))
    app.dependency_overrides[get_key_source] = FakeKeys
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_email] = lambda: mailbox
    return TestClient(app, raise_server_exceptions=False)


def cleanup_documents(db_engine, profile_id) -> None:
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM documents WHERE owner_profile_id = :id"), {"id": profile_id})
        conn.execute(text("DELETE FROM children WHERE parent_id = :id"), {"id": profile_id})
        for table, column in (("legal_acceptances", "profile_id"), ("consents", "parent_id")):
            conn.execute(text(f"DELETE FROM {table} WHERE {column} = :id"), {"id": profile_id})
        conn.execute(text("DELETE FROM profiles WHERE id = :id"), {"id": profile_id})


@pytest.fixture
def parent(client, db_engine, user):  # noqa: F811
    assert client.post("/me/profile", json=PARENT, headers=auth_for(user)).status_code == 201
    yield user
    cleanup_documents(db_engine, user["id"])


@pytest.fixture
def sitter(client, db_engine):
    # A fresh identity, not `user`: this fixture and `parent` are sometimes both needed in one test
    # (e.g. one account trying to touch another's document), so they must never be the same person.
    identity = {"id": uuid.uuid4(), "email": f"sitter-{uuid.uuid4()}@example.com"}
    body = {**PARENT, "role": "sitter"}
    assert client.post("/me/profile", json=body, headers=auth_for(identity)).status_code == 201
    assert fill_details(client, identity).status_code == 200
    yield identity
    cleanup_documents(db_engine, identity["id"])


@pytest.fixture
def other_parent(client, db_engine):
    other = {"id": uuid.uuid4(), "email": f"other-{uuid.uuid4()}@example.com"}
    assert client.post("/me/profile", json=PARENT, headers=auth_for(other)).status_code == 201
    yield other
    cleanup_documents(db_engine, other["id"])


@pytest.fixture
def admin(make_profile, db_engine):  # noqa: F811
    admin_id = make_profile("admin", "active")
    yield admin_id
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM document_access_log WHERE admin_id = :id"), {"id": admin_id})


def add_child(db_engine, parent_id) -> uuid.UUID:
    child_id = uuid.uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO children (id, parent_id, name, date_of_birth) VALUES (:id, :p, 'Asha', '2023-01-01')"),
            {"id": child_id, "p": parent_id},
        )
    return child_id


def request_upload(client, user, doc_type="government_id", child_id=None):  # noqa: F811
    body = {"type": doc_type}
    if child_id is not None:
        body["child_id"] = str(child_id)
    return client.post("/documents/upload-url", json=body, headers=auth_for(user))


def accept_consent(client, user):  # noqa: F811
    return client.post(
        "/parent/consent",
        json={"version": consent.CONSENT_VERSION, "marketing": False, "accepted": ACCEPTED},
        headers=auth_for(user),
    )


def row(db_engine, sql: str, **params):
    with db_engine.connect() as conn:
        return conn.execute(text(sql), params).mappings().one()


def rows(db_engine, sql: str, **params):
    with db_engine.connect() as conn:
        return conn.execute(text(sql), params).mappings().all()


def scalar(db_engine, sql: str, **params):
    with db_engine.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


# ---------- sniffing (pure function) ----------


@pytest.mark.parametrize(
    ("data", "expected"),
    [(PDF, "application/pdf"), (JPEG, "image/jpeg"), (PNG, "image/png"), (NOT_A_DOCUMENT, None), (b"", None)],
)
def test_sniff_content_type(data, expected):
    assert sniff_content_type(data) == expected


# ---------- requesting an upload URL ----------


def test_a_parent_gets_a_signed_upload_url(client, db_engine, parent):  # noqa: F811
    response = request_upload(client, parent, "government_id")
    assert response.status_code == 201
    body = response.json()
    assert body["upload_url"] == f"https://fake.storage/upload/{parent['id']}/{body['document_id']}?token=test-upload"
    found = row(
        db_engine,
        "SELECT owner_profile_id, type, status, storage_path FROM documents WHERE id = :id",
        id=body["document_id"],
    )
    assert str(found["owner_profile_id"]) == str(parent["id"])
    assert found["type"] == "government_id"
    assert found["status"] == "pending_upload"
    assert found["storage_path"] == f"{parent['id']}/{body['document_id']}"


def test_a_sitter_gets_a_signed_upload_url(client, sitter):  # noqa: F811
    assert request_upload(client, sitter, "police_certificate").status_code == 201


def test_a_birth_certificate_needs_the_current_consent_first(client, db_engine, parent):  # noqa: F811
    """CLAUDE.md 9 ("Consent"): child document upload refused without an accepted consent."""
    child_id = add_child(db_engine, parent["id"])
    response = request_upload(client, parent, "birth_certificate", child_id)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "consent_required"


def test_a_birth_certificate_can_be_attached_to_the_parents_own_child(client, db_engine, parent):  # noqa: F811
    child_id = add_child(db_engine, parent["id"])
    assert accept_consent(client, parent).status_code == 200
    response = request_upload(client, parent, "birth_certificate", child_id)
    assert response.status_code == 201
    found = row(db_engine, "SELECT child_id FROM documents WHERE id = :id", id=response.json()["document_id"])
    assert str(found["child_id"]) == str(child_id)


def test_cannot_attach_a_document_to_someone_elses_child(client, db_engine, parent, other_parent):  # noqa: F811
    other_child = add_child(db_engine, other_parent["id"])
    response = request_upload(client, parent, "birth_certificate", other_child)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_a_made_up_child_id_is_refused(client, parent):  # noqa: F811
    response = request_upload(client, parent, "birth_certificate", uuid.uuid4())
    assert response.status_code == 403


# ---------- confirming an upload ----------


def confirm(client, user, document_id):  # noqa: F811
    return client.post(f"/documents/{document_id}/confirm", headers=auth_for(user))


@pytest.mark.parametrize(("content", "mime"), [(PDF, "application/pdf"), (JPEG, "image/jpeg"), (PNG, "image/png")])
def test_confirming_a_real_file_marks_it_uploaded(client, db_engine, storage, parent, content, mime):  # noqa: F811
    ticket = request_upload(client, parent).json()
    storage.put(f"{parent['id']}/{ticket['document_id']}", content)

    response = confirm(client, parent, ticket["document_id"])
    assert response.status_code == 200
    assert response.json() == {"status": "uploaded"}
    assert scalar(db_engine, "SELECT status FROM documents WHERE id = :id", id=ticket["document_id"]) == "uploaded"


def test_confirming_something_that_isnt_a_pdf_jpg_or_png_is_rejected(client, db_engine, storage, parent):  # noqa: F811
    ticket = request_upload(client, parent).json()
    storage.put(f"{parent['id']}/{ticket['document_id']}", NOT_A_DOCUMENT)

    response = confirm(client, parent, ticket["document_id"])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_file"
    assert "PDF, JPG or PNG" in response.json()["error"]["message"]
    assert storage.deleted == [f"{parent['id']}/{ticket['document_id']}"]
    assert scalar(db_engine, "SELECT status FROM documents WHERE id = :id", id=ticket["document_id"]) == "invalid"


def test_a_file_declaring_a_real_type_but_too_big_is_rejected(client, storage, parent):  # noqa: F811
    ticket = request_upload(client, parent).json()
    storage.put(f"{parent['id']}/{ticket['document_id']}", OVERSIZED_PDF)

    response = confirm(client, parent, ticket["document_id"])
    assert response.status_code == 422
    assert "larger than 5 MB" in response.json()["error"]["message"]


def test_confirming_before_uploading_anything_is_refused(client, parent):  # noqa: F811
    ticket = request_upload(client, parent).json()
    response = confirm(client, parent, ticket["document_id"])
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "upload_not_found"


def test_confirming_twice_is_refused_the_second_time(client, storage, parent):  # noqa: F811
    ticket = request_upload(client, parent).json()
    storage.put(f"{parent['id']}/{ticket['document_id']}", PDF)
    assert confirm(client, parent, ticket["document_id"]).status_code == 200
    again = confirm(client, parent, ticket["document_id"])
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "already_confirmed"


def test_someone_elses_document_cannot_be_confirmed(client, storage, parent, sitter):  # noqa: F811
    """No IDOR: changing the id in the URL doesn't let you touch another account's document."""
    ticket = request_upload(client, parent).json()
    storage.put(f"{parent['id']}/{ticket['document_id']}", PDF)
    response = confirm(client, sitter, ticket["document_id"])
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_confirming_a_document_that_doesnt_exist_is_404(client, parent):  # noqa: F811
    response = confirm(client, parent, uuid.uuid4())
    assert response.status_code == 404


# ---------- listing my own documents ----------


def test_listing_my_documents_shows_status(client, storage, parent):  # noqa: F811
    police_cert = request_upload(client, parent, "police_certificate").json()
    government_id = request_upload(client, parent, "government_id").json()
    storage.put(f"{parent['id']}/{police_cert['document_id']}", PDF)
    confirm(client, parent, police_cert["document_id"])

    listed = client.get("/documents/mine", headers=auth_for(parent)).json()
    by_id = {d["id"]: d for d in listed}
    assert by_id[police_cert["document_id"]]["status"] == "uploaded"
    assert by_id[police_cert["document_id"]]["type"] == "police_certificate"
    assert by_id[government_id["document_id"]]["status"] == "pending_upload"


def test_listing_my_documents_can_be_filtered_by_type(client, parent):  # noqa: F811
    request_upload(client, parent, "police_certificate")
    request_upload(client, parent, "government_id")
    listed = client.get("/documents/mine?type=police_certificate", headers=auth_for(parent)).json()
    assert {d["type"] for d in listed} == {"police_certificate"}


def test_a_sitters_documents_dont_show_in_a_parents_list(client, parent, sitter):  # noqa: F811
    request_upload(client, sitter, "government_id")
    assert client.get("/documents/mine", headers=auth_for(parent)).json() == []


# ---------- admin viewing ----------


def test_an_admin_gets_a_signed_view_url_and_it_is_logged(client, db_engine, storage, parent, admin):  # noqa: F811
    ticket = request_upload(client, parent).json()

    response = client.get(f"/admin/documents/{ticket['document_id']}/view-url", headers=as_user(admin))
    assert response.status_code == 200
    expected_url = f"https://fake.storage/view/{parent['id']}/{ticket['document_id']}?token=test-view"
    assert response.json() == {"url": expected_url}

    found = rows(
        db_engine, "SELECT admin_id FROM document_access_log WHERE document_id = :id", id=ticket["document_id"]
    )
    assert [str(entry["admin_id"]) for entry in found] == [str(admin)]


def test_a_second_view_logs_again(client, db_engine, parent, admin):  # noqa: F811
    ticket = request_upload(client, parent).json()
    url = f"/admin/documents/{ticket['document_id']}/view-url"
    assert client.get(url, headers=as_user(admin)).status_code == 200
    assert client.get(url, headers=as_user(admin)).status_code == 200
    # two separate rows, not deduplicated or updated (CLAUDE.md 5: every view is logged)
    found = rows(
        db_engine, "SELECT admin_id FROM document_access_log WHERE document_id = :id", id=ticket["document_id"]
    )
    assert len(found) == 2


@pytest.mark.parametrize("role", ["parent", "sitter"])
def test_non_admins_cannot_get_a_view_url(client, parent, make_profile, role):  # noqa: F811
    ticket = request_upload(client, parent).json()
    caller = parent if role == "parent" else make_profile("sitter")
    headers = auth_for(caller) if role == "parent" else as_user(caller)
    response = client.get(f"/admin/documents/{ticket['document_id']}/view-url", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_viewing_a_document_that_doesnt_exist_is_404(client, admin):  # noqa: F811
    response = client.get(f"/admin/documents/{uuid.uuid4()}/view-url", headers=as_user(admin))
    assert response.status_code == 404
