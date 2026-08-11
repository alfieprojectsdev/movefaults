"""Add content_sha256 to logsheet_photos for upload idempotency

The photo endpoint had no idempotency guard, unlike the logsheet POST
(ON CONFLICT client_uuid DO NOTHING). That asymmetry is a real problem in the
field: a client cannot distinguish "the upload failed" from "the upload
succeeded and the response was lost on the way back", which is the ordinary
failure on a weak link. Every retry after the second case stored the same image
again — one observation ending up with several R2 objects and several rows.

Duplicate photos cost storage, but the real damage is provenance: which of two
near-identical images was the one the observer meant?

Content hash rather than a client-supplied id, because it needs no cooperation
from the client and it dedupes the exact case that matters — a retry sends
identical bytes. Scoped per logsheet: the same image legitimately attached to
two different station visits stays two rows.

Revision ID: 014
Revises: 013
"""

import sqlalchemy as sa
from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None

SCHEMA = "field_ops"


def upgrade() -> None:
    op.add_column(
        "logsheet_photos",
        sa.Column("content_sha256", sa.Text(), nullable=True),
        schema=SCHEMA,
    )

    # Partial unique index: existing rows predate hashing and carry NULL, and
    # NULLs do not collide in a unique index, so this can be added without
    # backfilling. New uploads all carry a hash and are deduped from here on.
    op.create_index(
        "uq_logsheet_photos_logsheet_sha256",
        "logsheet_photos",
        ["logsheet_id", "content_sha256"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("content_sha256 IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_logsheet_photos_logsheet_sha256",
        table_name="logsheet_photos",
        schema=SCHEMA,
    )
    op.drop_column("logsheet_photos", "content_sha256", schema=SCHEMA)
