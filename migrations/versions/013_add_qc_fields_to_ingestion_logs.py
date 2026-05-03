"""Add QC fields to ingestion_logs

Revision ID: 013
Revises: 012
Create Date: 2026-05-02
"""
import sqlalchemy as sa
from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ingestion_logs", sa.Column("qc_obs_count",   sa.Integer(), nullable=True))
    op.add_column("ingestion_logs", sa.Column("qc_cycle_slips", sa.Integer(), nullable=True))
    op.add_column("ingestion_logs", sa.Column("qc_mp1_rms",     sa.Float(),   nullable=True))
    op.add_column("ingestion_logs", sa.Column("qc_mp2_rms",     sa.Float(),   nullable=True))


def downgrade() -> None:
    op.drop_column("ingestion_logs", "qc_mp2_rms")
    op.drop_column("ingestion_logs", "qc_mp1_rms")
    op.drop_column("ingestion_logs", "qc_cycle_slips")
    op.drop_column("ingestion_logs", "qc_obs_count")
