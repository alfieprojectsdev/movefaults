"""drop unused plumbing_offset_mm (contract half of fo004)

Revision ID: fo005
Revises: fo004
Create Date: 2026-08-20 UTC

The contract half of the expand/contract pair started in fo004.

plumbing_offset_mm was added by root revision 008, alongside bubble_centred, to
mirror the "Offset of plumbing observation ___ mm" box on the paper campaign
form. bubble_centred is used; this one never was — confirmed 2026-08-20.

APPLY THIS ONLY AFTER THE NEW API IS DEPLOYED.
----------------------------------------------
Kept separate from fo004 because a running service that still lists the column
in its SQLAlchemy model will name it in every INSERT. Dropping it underneath
that code turns every logsheet submission into a 500 — and the failure lands on
the offline queue, which treats a 5xx as transient and retries forever, so the
field sees sheets that never sync rather than an error anyone can act on.

Order: fo004 (add) → deploy → fo005 (drop).

No data is lost: field_ops.logsheets is empty at the time of writing, and the
column was never populated by the PWA in any case. The downgrade re-adds the
column, not its contents — there are none to restore.
"""

from alembic import op

revision = "fo005"
down_revision = "fo004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE field_ops.logsheets DROP COLUMN IF EXISTS plumbing_offset_mm")


def downgrade() -> None:
    op.execute("ALTER TABLE field_ops.logsheets ADD COLUMN plumbing_offset_mm FLOAT")
