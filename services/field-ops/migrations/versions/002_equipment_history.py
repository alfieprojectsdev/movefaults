"""create equipment_history table

Revision ID: fo002
Revises: fo001
Create Date: 2026-02-25 UTC

Creates field_ops.equipment_history — a temporal (SCD Type 2) record of hardware
installed at each CORS station over time.

Replaces the point-in-time limitation of field_ops.equipment_inventory for
historical queries. equipment_inventory remains for current QR-code lookups
and active equipment status; equipment_history is the archival ledger.

Key design choices:
  - date_installed / date_removed define the valid-time interval.
    date_removed IS NULL means the equipment is currently installed.
  - station_code is a loose TEXT reference (no FK) — consistent with the
    denormalization pattern used in logsheets and VADASE tables.
  - arp_height_m (Antenna Reference Point height above monument) and
    elevation_cutoff_deg are stored here because they feed Bernese .STA
    file generation — this is the authoritative source for those values.
  - satellite_systems is TEXT (e.g. 'GPS', 'GPS+GLONASS', 'GNSS') rather
    than an array; the vocabulary is small and queried by equality.
"""

from alembic import op

revision = "fo002"
down_revision = "fo001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE field_ops.equipment_history (
            id                      SERIAL          PRIMARY KEY,
            station_code            VARCHAR(10)     NOT NULL,

            -- Hardware classification
            equipment_type          VARCHAR(100),                   -- GNSS Receiver | Antenna | Cable | etc.
            serial_number           VARCHAR(100),

            -- Receiver details
            manufacturer            VARCHAR(100),
            model                   VARCHAR(100),
            firmware_version        VARCHAR(50),
            num_channels            INTEGER,

            -- Antenna details
            antenna_manufacturer    VARCHAR(100),
            antenna_model           VARCHAR(100),                   -- e.g. TRM41249.00
            radome_type             VARCHAR(50),

            -- Installation specs (Bernese .STA inputs)
            antenna_location        VARCHAR(100),                   -- Rooftop | Ground | Pillar
            cable_length_m          FLOAT,
            elevation_cutoff_deg    FLOAT,
            arp_height_m            FLOAT,                          -- Antenna Reference Point height above monument

            -- Infrastructure
            power_source            VARCHAR(100),                   -- Solar | AC-DC | Battery | Solar+Battery
            has_internet            BOOLEAN,
            has_lightning_rod       BOOLEAN,

            -- Constellation support
            satellite_systems       TEXT,                           -- GPS | GNSS | GPS+GLONASS

            -- Valid-time interval (SCD Type 2)
            date_installed          DATE,                           -- NULL = unknown start date
            date_removed            DATE,                           -- NULL = currently installed

            notes                   TEXT,
            created_at              TIMESTAMPTZ     DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Index for the primary historical query: equipment at station X on date Y
    op.execute("""
        CREATE INDEX idx_equip_history_station
            ON field_ops.equipment_history (station_code, date_installed, date_removed)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS field_ops.equipment_history")
