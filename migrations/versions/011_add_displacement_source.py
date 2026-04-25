"""Add displacement_source TEXT NULL to vadase_displacements

Revision ID: 011
Revises: 010
Create Date: 2026-04-25 UTC

Persists the ReceiverMode state machine decision for each displacement row.
Values written by IngestionCore.handle_displacement():
  'RECEIVER'         -- receiver's own integrated displacement; state machine in RECEIVER mode
  'RECEIVER_SUSPECT' -- RECEIVER mode but suspect_streak > 0 (possible scintillation)
  'INTEGRATOR'       -- manual leaky-integrator output; state machine in MANUAL mode

Nullable because rows ingested before this migration have no source annotation.
TEXT rather than an ENUM to avoid schema churn during active ReceiverMode iteration
(DL-001 from plan 3488e63d).
"""

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE vadase_displacements "
        "ADD COLUMN displacement_source TEXT NULL"
    )
    op.execute(
        "COMMENT ON COLUMN vadase_displacements.displacement_source IS "
        "'ReceiverMode decision: RECEIVER | RECEIVER_SUSPECT | INTEGRATOR. "
        "NULL for rows ingested before migration 011.'"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE vadase_displacements DROP COLUMN IF EXISTS displacement_source"
    )
