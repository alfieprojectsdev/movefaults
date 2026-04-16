"""rename rinex_files.hash_md5 to hash_sha256

Revision ID: 009
Revises: 008
Create Date: 2026-04-16 UTC

The ingestion pipeline's SHA-256 hash (stored in ingestion_logs.file_hash)
was never linked to the MD5 stored in rinex_files.hash_md5 — two separate
hash algorithms meant a file's identity could not be confirmed across the
two tables. This migration aligns both tables on SHA-256:

  - Renames hash_md5  VARCHAR(32) → hash_sha256 VARCHAR(64)
  - Existing rows have hash_md5 values copied in-place. Because MD5 is
    32 hex chars and SHA-256 is 64, existing values are NOT valid SHA-256
    hashes. They are preserved rather than NULLed so that any forensic
    audit of legacy ingestion runs can still identify the source file.
    Re-ingesting the file (if needed) will overwrite with a real SHA-256.
"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename the column and widen to 64 chars (SHA-256 hex digest length)
    op.alter_column(
        "rinex_files",
        "hash_md5",
        new_column_name="hash_sha256",
        type_=sa.String(64),
        existing_type=sa.String(32),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Narrow back to 32 chars and restore original name.
    # Values longer than 32 chars (real SHA-256 hashes written after the
    # upgrade) will be truncated. Acceptable for a rollback scenario.
    op.alter_column(
        "rinex_files",
        "hash_sha256",
        new_column_name="hash_md5",
        type_=sa.String(32),
        existing_type=sa.String(64),
        existing_nullable=True,
    )
