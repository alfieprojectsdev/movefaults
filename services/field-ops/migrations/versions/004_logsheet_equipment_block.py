"""logsheet equipment before/after block (expand half)

Revision ID: fo004
Revises: fo003
Create Date: 2026-08-20 UTC

Adds the equipment block from the paper "GPS Station Maintenance Record" — the
BTU2-style form used on continuous (CORS) visits, which is structured as a
Before/After table over receiver and antenna identity.

Why this belongs in the FIELD-OPS tree, not the root tree
---------------------------------------------------------
Every other field_ops.logsheets column was added by root revision 008. This one
is not, on purpose: the deployed Neon branch sits at root **011**, because root
012 sets `timescaledb.compress` and Neon reports `timescaledb.license = apache`
and refuses. Alembic runs the upgrade in one transaction, so 012 failing rolls
back everything after it and the root tree cannot advance past 011 on Neon at
all.

A revision 014 in the root tree would therefore apply on a local Postgres and
never in production, with nothing reporting a problem — the API would 500 on a
column that exists in the model and not in the database. The field-ops tree is
at fo003 and applies cleanly, so schema changes to field_ops go here until the
012 blocker is resolved.

What the columns are for
------------------------
An unrecorded receiver or antenna swap is one of the few things that puts a
genuine discontinuity into a coordinate series while looking like tectonics.
field_ops.equipment_history is the authoritative ledger for Bernese .STA
generation, but it is a temporal (SCD Type 2) table and this data arrives from
an offline queue that replays records days later — writing intervals straight
from a replayable source would produce duplicate and overlapping rows with
nothing to reconcile against.

So the logsheet records the *observation* (what was found installed, and what it
was changed to) and reconciliation into equipment_history stays a deliberate
office step. That also matches how the paper works: the sheet is the source
document, and someone later updates the station record from it.

`_before` is what the observer found on arrival — the single most valuable field
for the Palawan sites, where PPPC, PNDO and PKLY currently have **no**
equipment_history rows at all. `_after` is filled only when something changed.

antenna_type_before vs the existing antenna_model
-------------------------------------------------
They are different fields and must not be merged. `antenna_model` is
campaign-only, VARCHAR(20), and holds an IGS/ANTEX key from a fixed dropdown
(TRM41249.00 and friends) because it selects the constants that drive the RINEX
height reduction. `antenna_type_before/after` is free text for whatever is bolted
to a CORS monument — "Leica AR20" on BTU2 — which has no entry in that dropdown
and no reduction to drive.

This revision only ADDS
-----------------------
plumbing_offset_mm is unused in practice (confirmed 2026-08-20) and is dropped
by fo005, deliberately in a separate revision. Dropping it here would break the
API that is *currently running*: the deployed service still has the column in
its model, so its INSERT names it, and the drop would take effect while that
code is still serving.

Expand first, contract after the new code is live:

  1. fo004 (this)  — add columns. Harmless to the running service, which simply
                     never mentions them.
  2. deploy        — the new code starts using them.
  3. fo005         — drop plumbing_offset_mm, once nothing references it.

Adding columns is safe in the other direction too: a NOT NULL column with no
default would not be, which is why every one of these is nullable.
"""

from alembic import op

revision = "fo004"
down_revision = "fo003"
branch_labels = None
depends_on = None


# (column, type) — the Before/After pairs are generated from this so the two
# halves cannot drift apart, which is exactly the kind of asymmetry that makes
# a "changed" record unreadable later.
_EQUIPMENT_FIELDS = [
    ("receiver_model", "VARCHAR(100)"),
    ("receiver_serial", "VARCHAR(100)"),
    ("receiver_firmware", "VARCHAR(50)"),
    ("antenna_type", "VARCHAR(100)"),
    ("antenna_part_number", "VARCHAR(100)"),
    ("antenna_serial", "VARCHAR(100)"),
    ("antenna_height_m", "FLOAT"),
]


def _pair_names(name: str) -> tuple[str, str]:
    # antenna_height_m reads badly with a trailing suffix, so the unit stays last.
    if name.endswith("_m"):
        stem = name[:-2]
        return f"{stem}_before_m", f"{stem}_after_m"
    return f"{name}_before", f"{name}_after"


def upgrade() -> None:
    cols = ["ADD COLUMN equipment_changed BOOLEAN"]
    for name, sqltype in _EQUIPMENT_FIELDS:
        before, after = _pair_names(name)
        cols.append(f"ADD COLUMN {before} {sqltype}")
        cols.append(f"ADD COLUMN {after} {sqltype}")

    op.execute(f"ALTER TABLE field_ops.logsheets {', '.join(cols)}")


def downgrade() -> None:
    drops = ["DROP COLUMN IF EXISTS equipment_changed"]
    for name, _ in _EQUIPMENT_FIELDS:
        before, after = _pair_names(name)
        drops.append(f"DROP COLUMN IF EXISTS {before}")
        drops.append(f"DROP COLUMN IF EXISTS {after}")

    op.execute(f"ALTER TABLE field_ops.logsheets {', '.join(drops)}")
