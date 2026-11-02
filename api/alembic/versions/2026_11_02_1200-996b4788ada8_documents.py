"""documents

Private file storage for verification documents (CLAUDE.md sections 5, 7 and 8): a `documents` row
per uploaded file, and an append-only `document_access_log` row per admin view. The actual bytes
live in a private Supabase Storage bucket, `documents`, created here too (only on Supabase: a local
or CI Postgres has no `storage` schema, so that part is skipped there). The bucket itself also
enforces the 5 MB / PDF-JPG-PNG limits so a client can never reach Storage with something else; the
API checks the real file content again on confirm, since content type here is declared, not sniffed.

Like every table: RLS on with no policies, nothing for the browser roles.

Revision ID: 996b4788ada8
Revises: 04054f1dc8b3
Create Date: 2026-11-02 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

API_ROLE = "pacifyco_api"
BROWSER_ROLES = ["anon", "authenticated"]
TABLES = ["documents", "document_access_log"]

BUCKET_ID = "documents"
MAX_FILE_BYTES = 5 * 1024 * 1024
ALLOWED_MIME_TYPES = ["application/pdf", "image/jpeg", "image/png"]

# revision identifiers, used by Alembic.
revision: str = "996b4788ada8"
down_revision: str | Sequence[str] | None = "04054f1dc8b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_profile_id", sa.Uuid(), nullable=False),
        sa.Column("child_id", sa.Uuid(), nullable=True),
        sa.Column(
            "type",
            sa.Enum(
                "aadhaar_masked",
                "birth_certificate",
                "government_id",
                "college_or_work_id",
                "police_certificate",
                "first_aid_certificate",
                "doctor_note",
                "photo",
                name="document_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending_upload",
                "uploaded",
                "invalid",
                name="document_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="pending_upload",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_profile_id"], ["profiles.id"], name=op.f("fk_documents_owner_profile_id_profiles"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["child_id"], ["children.id"], name=op.f("fk_documents_child_id_children"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("storage_path", name=op.f("uq_documents_storage_path")),
    )
    op.create_index(op.f("ix_documents_owner_profile_id"), "documents", ["owner_profile_id"], unique=False)
    op.create_index(op.f("ix_documents_child_id"), "documents", ["child_id"], unique=False)

    op.create_table(
        "document_access_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("admin_id", sa.Uuid(), nullable=False),
        sa.Column("accessed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], name=op.f("fk_document_access_log_document_id_documents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["admin_id"], ["profiles.id"], name=op.f("fk_document_access_log_admin_id_profiles"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_access_log")),
    )
    op.create_index(op.f("ix_document_access_log_document_id"), "document_access_log", ["document_id"], unique=False)
    op.create_index(op.f("ix_document_access_log_admin_id"), "document_access_log", ["admin_id"], unique=False)

    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    for role in BROWSER_ROLES:
        names = ", ".join(f'"{table}"' for table in TABLES)
        op.execute(
            f"""
            DO $$ BEGIN
              IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                REVOKE ALL ON {names} FROM {role};
              END IF;
            END $$;
            """
        )
    # The API role gets SELECT/INSERT/UPDATE/DELETE automatically (default privileges); the access
    # log can only be added to.
    op.execute(f'REVOKE UPDATE, DELETE ON "document_access_log" FROM {API_ROLE}')

    # Only a real Supabase project has a `storage` schema; a plain local/CI Postgres doesn't, so this
    # is skipped there and the migration still runs cleanly on an empty database.
    mime_list = ", ".join(f"'{mime}'" for mime in ALLOWED_MIME_TYPES)
    op.execute(
        f"""
        DO $$ BEGIN
          IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'storage' AND table_name = 'buckets') THEN
            INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
            VALUES ('{BUCKET_ID}', '{BUCKET_ID}', false, {MAX_FILE_BYTES}, ARRAY[{mime_list}])
            ON CONFLICT (id) DO NOTHING;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$ BEGIN
          IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'storage' AND table_name = 'buckets') THEN
            DELETE FROM storage.buckets WHERE id = '{BUCKET_ID}';
          END IF;
        END $$;
        """
    )
    op.drop_index(op.f("ix_document_access_log_admin_id"), table_name="document_access_log")
    op.drop_index(op.f("ix_document_access_log_document_id"), table_name="document_access_log")
    op.drop_table("document_access_log")
    op.drop_index(op.f("ix_documents_child_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_owner_profile_id"), table_name="documents")
    op.drop_table("documents")
