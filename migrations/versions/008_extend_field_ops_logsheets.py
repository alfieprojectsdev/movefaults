"""extend field_ops schema — staff table, observer junction, and logsheet columns

Revision ID: 008
Revises: 007
Create Date: 2026-03-02 UTC

Extends the field_ops schema with three coordinated changes that bring the
digital logsheet in line with the paper forms collected during campaign GPS.

---

field_ops.staff
---------------
Replaces free-text observer names (e.g. "ZH, EW" in a notes field) with a
proper reference table. Paper forms consistently show multiple sets of
initials in the "Prepared by" block — this table is the backing entity for
those initials. The `role` column distinguishes field collectors from data
processors and admins, which matters for workflow routing in the PWA.

field_ops.logsheet_observers
----------------------------
Many-to-many junction between logsheets and staff. A single field session
routinely involves multiple observers (e.g. the BTU2 form shows "ZH, EW").
Modelling this as a junction table — rather than a comma-separated column —
makes it possible to query "all logsheets observer ZH participated in" without
text parsing. ON DELETE CASCADE on logsheet_id: if a logsheet is deleted its
observer links are automatically removed (the link has no meaning without the
parent). ON DELETE RESTRICT on staff_id: a staff record cannot be deleted
while any historical logsheet references it — preserving the audit trail.

monitoring_method column
------------------------
The PWA renders one of two form modes depending on whether the station visit
is a campaign GPS deployment or a continuous (CORS) maintenance check. The
set of meaningful fields differs substantially between the two modes. Storing
monitoring_method in the DB (rather than inferring it from station_code)
makes the form mode an explicit, auditable field and simplifies backend
validation: required columns can be checked against this value.

Continuous-only columns
-----------------------
power_notes / battery_voltage_v / battery_voltage_source / temperature_c /
temperature_source capture the power and environment block present on the
CORS maintenance logsheet. battery_voltage_v and temperature_c are nullable
floats so that:
  (a) existing rows (created before this migration) remain valid with NULLs,
  (b) future sensor telemetry and manual entry use the same column without
      another migration.
The *_source columns (manual | sensor) allow the backend to flag whether a
value came from a human reading or an automated sensor poll. This supports
the roadmap goal of replacing manual station health checks with sensor
telemetry — the schema is ready; only the ingestor changes.

Campaign-only columns
---------------------
antenna_model / slant_{n,s,e,w}_m / avg_slant_m capture the physical
measurements recorded by field staff for the antenna setup. These are the
raw inputs to the RINEX height formula.

rinex_height_m stores the computed result:
    RH = SQRT(avg_slant_m² - C²) - VO
where C is the antenna constant and VO is the vertical offset for the
antenna model. Storing the computed value — rather than re-computing it
during processing — creates a self-contained audit record: if the antenna
constant table changes in the future, historical logsheets still show
the height that was actually used.

session_id (format: SITE+DOY, e.g. BUCA342, optionally BUCA342-02 for a
mid-session equipment change) matches Bernese campaign naming conventions.
The orchestrator can use this field to verify that the field logsheet and
the Bernese campaign directory refer to the same session without string
manipulation.

utc_start / utc_end / bubble_centred / plumbing_offset_mm complete the
standard campaign logsheet fields needed for Bernese .STA file generation.

downgrade()
-----------
Drops tables and columns in dependency order: junction first, then the new
tables and columns. Uses IF EXISTS throughout so a partial upgrade can be
cleanly unwound.
"""

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. field_ops.staff — structured observer registry
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE field_ops.staff (
            id              SERIAL          PRIMARY KEY,
            full_name       VARCHAR(200)    NOT NULL,
            initials        VARCHAR(10),
            -- role vocabulary: field_staff | data_processor | admin
            role            VARCHAR(50)     NOT NULL DEFAULT 'field_staff',
            is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMPTZ     DEFAULT NOW()
        )
    """)

    # Fast filtered lookup for dropdown population — only active staff shown in PWA
    op.execute("""
        CREATE INDEX idx_staff_is_active
            ON field_ops.staff (is_active)
    """)

    # ------------------------------------------------------------------
    # 2. field_ops.logsheet_observers — many-to-many junction
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE field_ops.logsheet_observers (
            logsheet_id     INTEGER         NOT NULL
                                REFERENCES field_ops.logsheets(id) ON DELETE CASCADE,
            staff_id        INTEGER         NOT NULL
                                REFERENCES field_ops.staff(id) ON DELETE RESTRICT,
            PRIMARY KEY (logsheet_id, staff_id)
        )
    """)

    # ------------------------------------------------------------------
    # 3. ALTER field_ops.logsheets — shared column
    # ------------------------------------------------------------------

    # monitoring_method drives PWA form mode and backend validation
    # valid values: campaign | continuous
    op.execute("""
        ALTER TABLE field_ops.logsheets
            ADD COLUMN monitoring_method VARCHAR(20),
            ADD CONSTRAINT chk_logsheets_monitoring_method
                CHECK (monitoring_method IN ('campaign', 'continuous'))
    """)

    # ------------------------------------------------------------------
    # 4. ALTER field_ops.logsheets — continuous-only columns
    # ------------------------------------------------------------------
    op.execute("""
        ALTER TABLE field_ops.logsheets
            ADD COLUMN power_notes              TEXT,
            ADD COLUMN battery_voltage_v        FLOAT,
            ADD COLUMN battery_voltage_source   VARCHAR(10),
            ADD COLUMN temperature_c            FLOAT,
            ADD COLUMN temperature_source       VARCHAR(10),
            ADD CONSTRAINT chk_logsheets_battery_source
                CHECK (battery_voltage_source IN ('manual', 'sensor')),
            ADD CONSTRAINT chk_logsheets_temperature_source
                CHECK (temperature_source IN ('manual', 'sensor'))
    """)

    # ------------------------------------------------------------------
    # 5. ALTER field_ops.logsheets — campaign-only columns
    # ------------------------------------------------------------------
    op.execute("""
        ALTER TABLE field_ops.logsheets
            ADD COLUMN antenna_model        VARCHAR(20),
            ADD COLUMN slant_n_m            FLOAT,
            ADD COLUMN slant_s_m            FLOAT,
            ADD COLUMN slant_e_m            FLOAT,
            ADD COLUMN slant_w_m            FLOAT,
            ADD COLUMN avg_slant_m          FLOAT,
            -- Computed RINEX height RH = SQRT(avg_slant_m² - C²) - VO; stored for audit
            ADD COLUMN rinex_height_m       FLOAT,
            -- Format: SITE+DOY (e.g. BUCA342) or SITE+DOY-NN (e.g. BUCA342-02)
            ADD COLUMN session_id           VARCHAR(20),
            ADD COLUMN utc_start            TIMESTAMPTZ,
            ADD COLUMN utc_end              TIMESTAMPTZ,
            ADD COLUMN bubble_centred       BOOLEAN,
            ADD COLUMN plumbing_offset_mm   FLOAT
    """)


def downgrade() -> None:
    # Drop junction table first (depends on both logsheets and staff)
    op.execute("DROP TABLE IF EXISTS field_ops.logsheet_observers")

    # Drop staff table
    op.execute("DROP TABLE IF EXISTS field_ops.staff")

    # Remove campaign-only columns
    op.execute("""
        ALTER TABLE field_ops.logsheets
            DROP COLUMN IF EXISTS plumbing_offset_mm,
            DROP COLUMN IF EXISTS bubble_centred,
            DROP COLUMN IF EXISTS utc_end,
            DROP COLUMN IF EXISTS utc_start,
            DROP COLUMN IF EXISTS session_id,
            DROP COLUMN IF EXISTS rinex_height_m,
            DROP COLUMN IF EXISTS avg_slant_m,
            DROP COLUMN IF EXISTS slant_w_m,
            DROP COLUMN IF EXISTS slant_e_m,
            DROP COLUMN IF EXISTS slant_s_m,
            DROP COLUMN IF EXISTS slant_n_m,
            DROP COLUMN IF EXISTS antenna_model
    """)

    # Remove continuous-only columns and their constraints
    op.execute("""
        ALTER TABLE field_ops.logsheets
            DROP CONSTRAINT IF EXISTS chk_logsheets_temperature_source,
            DROP CONSTRAINT IF EXISTS chk_logsheets_battery_source,
            DROP COLUMN IF EXISTS temperature_source,
            DROP COLUMN IF EXISTS temperature_c,
            DROP COLUMN IF EXISTS battery_voltage_source,
            DROP COLUMN IF EXISTS battery_voltage_v,
            DROP COLUMN IF EXISTS power_notes
    """)

    # Remove shared column and its constraint
    op.execute("""
        ALTER TABLE field_ops.logsheets
            DROP CONSTRAINT IF EXISTS chk_logsheets_monitoring_method,
            DROP COLUMN IF EXISTS monitoring_method
    """)
