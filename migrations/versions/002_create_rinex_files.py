"""create rinex_files table

Revision ID: 002
Revises: 001
Create Date: 2026-02-24 UTC

Catalogue of RINEX observation files ingested into the system.

Design notes:
  - filepath has a UNIQUE constraint: same file (by path) cannot be ingested twice.
  - hash_md5 catches duplicates arriving at different paths (e.g. renamed files).
  - idx_rinex_station_time supports the most common query pattern: "give me all
    RINEX files for station X within date range Y-Z."
  - station_id is a FK to stations.id — rinex_files.station_id serves as the
    FK bridge between the text-based VADASE world and the integer-PK world here.
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rinex_files",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "station_id",
            sa.Integer(),
            sa.ForeignKey("stations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("filepath", sa.String(1024), nullable=False),
        sa.Column("start_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("end_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("sampling_interval", sa.Float(), nullable=True),
        sa.Column("receiver_type", sa.String(100), nullable=True),
        sa.Column("antenna_type", sa.String(100), nullable=True),
        sa.Column("hash_md5", sa.String(32), nullable=True),
        sa.Column(
            "date_added",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("filepath", name="uq_rinex_files_filepath"),
    )
    op.create_index(
        "idx_rinex_station_time",
        "rinex_files",
        ["station_id", "start_time"],
    )


def downgrade() -> None:
    op.drop_index("idx_rinex_station_time", table_name="rinex_files")
    op.drop_table("rinex_files")
