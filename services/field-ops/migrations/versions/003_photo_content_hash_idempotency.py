"""Add content_sha256 to logsheet_photos for upload idempotency

Revision ID: fo003
Revises: fo002
Create Date: 2026-08-11 UTC

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

Which tree this belongs to
--------------------------
This revision first landed in the ROOT alembic tree as `014`, which could not
work: field_ops.logsheet_photos is created by fo001 in THIS tree, and DEPLOY.md
runs the root tree first. On a fresh database the documented order failed at the
ADD COLUMN, because the table did not exist yet. A migration belongs in the tree
that owns its table — the two trees have separate alembic_version tables and no
ordering relationship between them.
"""

import sqlalchemy as sa
from alembic import op

revision = "fo003"
down_revision = "fo002"
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
