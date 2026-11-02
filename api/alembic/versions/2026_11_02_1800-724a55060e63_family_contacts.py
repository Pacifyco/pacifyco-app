"""family contacts

Family Terms 2.5 (CLAUDE.md section 7): emergency contacts move from per-child to per-family (two
per family, enforced by the API, not a database constraint -- `set_emergency_contacts` always
replaces both together). Adds `authorised_adults`: any number of named adults who may hand over or
receive a child during a booking. No real data to preserve (staging only, nothing in production).

Like every table: RLS on with no policies, nothing for the browser roles. Not append-only: a parent
can update their emergency contacts and remove an authorised adult.

Revision ID: 724a55060e63
Revises: d2d559d33cf0
Create Date: 2026-11-02 18:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

BROWSER_ROLES = ["anon", "authenticated"]
TABLES = ["emergency_contacts", "authorised_adults"]

# revision identifiers, used by Alembic.
revision: str = "724a55060e63"
down_revision: str | Sequence[str] | None = "d2d559d33cf0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def lock_down(tables: list[str]) -> None:
    for table in tables:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    for role in BROWSER_ROLES:
        names = ", ".join(f'"{table}"' for table in tables)
        op.execute(
            f"""
            DO $$ BEGIN
              IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                REVOKE ALL ON {names} FROM {role};
              END IF;
            END $$;
            """
        )


def upgrade() -> None:
    op.drop_index(op.f("ix_emergency_contacts_child_id"), table_name="emergency_contacts")
    op.drop_table("emergency_contacts")

    op.create_table(
        "emergency_contacts",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("relationship", sa.Text(), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["parents.profile_id"], name=op.f("fk_emergency_contacts_parent_id_parents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_emergency_contacts")),
    )
    op.create_index(op.f("ix_emergency_contacts_parent_id"), "emergency_contacts", ["parent_id"], unique=False)

    op.create_table(
        "authorised_adults",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("relationship", sa.Text(), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["parents.profile_id"], name=op.f("fk_authorised_adults_parent_id_parents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_authorised_adults")),
    )
    op.create_index(op.f("ix_authorised_adults_parent_id"), "authorised_adults", ["parent_id"], unique=False)

    lock_down(TABLES)


def downgrade() -> None:
    op.drop_index(op.f("ix_authorised_adults_parent_id"), table_name="authorised_adults")
    op.drop_table("authorised_adults")

    op.drop_index(op.f("ix_emergency_contacts_parent_id"), table_name="emergency_contacts")
    op.drop_table("emergency_contacts")

    op.create_table(
        "emergency_contacts",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("child_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("relationship", sa.Text(), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(
            ["child_id"], ["children.id"], name=op.f("fk_emergency_contacts_child_id_children"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_emergency_contacts")),
    )
    op.create_index(op.f("ix_emergency_contacts_child_id"), "emergency_contacts", ["child_id"], unique=False)
    op.execute('ALTER TABLE "emergency_contacts" ENABLE ROW LEVEL SECURITY')
    for role in BROWSER_ROLES:
        op.execute(
            f"""
            DO $$ BEGIN
              IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                REVOKE ALL ON "emergency_contacts" FROM {role};
              END IF;
            END $$;
            """
        )
