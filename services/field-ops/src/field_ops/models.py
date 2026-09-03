"""
SQLAlchemy ORM models for the field_ops PostgreSQL schema.

All tables live in the 'field_ops' schema namespace within the central POGF
database — logically isolated from the public schema (stations, rinex_files, etc.)
without requiring a separate database container.

Key design choices:
  - client_uuid on logsheets: UUID generated on the PWA before going offline.
    Enables idempotent sync — if the client retries after a network failure,
    ON CONFLICT (client_uuid) DO NOTHING prevents duplicate rows.
  - station_code on logsheets is a loose reference (TEXT, no FK) to public.stations.
    This avoids cross-schema FK complexity and matches VADASE's denorm pattern.
  - synced_at is NULL while the record is in the client's IndexedDB queue;
    it is set server-side when the POST /logsheets request succeeds.
"""

import uuid

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Column,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class FieldOpsBase(DeclarativeBase):
    """Separate Base from the central POGF schema so metadata stays isolated."""
    pass


SCHEMA = "field_ops"


class User(FieldOpsBase):
    """Field personnel accounts. Role controls admin-only endpoints."""

    __tablename__ = "users"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    hashed_password = Column(Text, nullable=False)
    role = Column(String(20), server_default="field_staff")  # field_staff | admin
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("CURRENT_TIMESTAMP"))

    logsheets = relationship("LogSheet", back_populates="submitter")

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role})>"


class LogSheet(FieldOpsBase):
    """
    One station visit record.

    The client generates client_uuid before submitting — this makes the sync
    endpoint naturally idempotent. Multiple offline records can be flushed in
    a single POST /logsheets batch call.
    """

    __tablename__ = "logsheets"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_uuid = Column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    station_code = Column(String(10), nullable=False)   # loose ref to public.stations
    submitted_by = Column(Integer, ForeignKey(f"{SCHEMA}.users.id"))
    visit_date = Column(Date, nullable=False)
    arrival_time = Column(TIMESTAMP(timezone=True))
    departure_time = Column(TIMESTAMP(timezone=True))
    weather_conditions = Column(Text)
    maintenance_performed = Column(Text)
    equipment_status = Column(String(50))  # ok | issue_found | repaired
    notes = Column(Text)
    synced_at = Column(TIMESTAMP(timezone=True))       # NULL = still in offline queue
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("CURRENT_TIMESTAMP"))

    # --- Mode discriminator ---
    monitoring_method = Column(String(20))   # campaign | continuous

    # --- Continuous-only ---
    power_notes = Column(Text)
    battery_voltage_v = Column(Float)
    battery_voltage_source = Column(String(10))   # manual | sensor
    temperature_c = Column(Float)
    temperature_source = Column(String(10))        # manual | sensor

    # --- Campaign-only ---
    antenna_model = Column(String(20))
    slant_n_m = Column(Float)
    slant_s_m = Column(Float)
    slant_e_m = Column(Float)
    slant_w_m = Column(Float)
    avg_slant_m = Column(Float)
    rinex_height_m = Column(Float)   # RH = SQRT(avg_slant² - C²) - VO; stored for audit trail
    session_id = Column(String(20))  # e.g. BUCA342 or BUCA342-02
    utc_start = Column(TIMESTAMP(timezone=True))
    utc_end = Column(TIMESTAMP(timezone=True))
    bubble_centred = Column(Boolean)

    # --- Equipment, as found and as left (continuous/CORS maintenance) ---
    #
    # Mirrors the Before/After table on the paper GPS Station Maintenance
    # Record. `_before` is what the observer found installed; `_after` is filled
    # only when something was swapped during the visit.
    #
    # This is the field OBSERVATION. equipment_history remains the authoritative
    # ledger for Bernese .STA generation, and is reconciled from these rows
    # deliberately rather than written from the offline queue, which replays
    # records days late and would produce overlapping validity intervals.
    #
    # antenna_type_before is NOT antenna_model. antenna_model is campaign-only
    # and holds an ANTEX key from a fixed dropdown because it selects the
    # constants driving the height reduction; this is free text for whatever is
    # on a CORS monument ("Leica AR20"), which has no dropdown entry.
    equipment_changed = Column(Boolean)
    receiver_model_before = Column(String(100))
    receiver_model_after = Column(String(100))
    receiver_serial_before = Column(String(100))
    receiver_serial_after = Column(String(100))
    receiver_firmware_before = Column(String(50))
    receiver_firmware_after = Column(String(50))
    antenna_type_before = Column(String(100))
    antenna_type_after = Column(String(100))
    antenna_part_number_before = Column(String(100))
    antenna_part_number_after = Column(String(100))
    antenna_serial_before = Column(String(100))
    antenna_serial_after = Column(String(100))
    antenna_height_before_m = Column(Float)
    antenna_height_after_m = Column(Float)

    submitter = relationship("User", back_populates="logsheets")
    photos = relationship("LogSheetPhoto", back_populates="logsheet")
    observers = relationship("LogSheetObserver", back_populates="logsheet")

    def __repr__(self) -> str:
        return f"<LogSheet {self.station_code} {self.visit_date} [{self.client_uuid}]>"


class Staff(FieldOpsBase):
    """
    PHIVOLCS staff who can be recorded as observers on a logsheet.

    Decoupled from the User table deliberately: a Staff row represents a real
    person (field technician, data processor) even if they have no login
    account. The many-to-many link to LogSheet is through LogSheetObserver.
    """

    __tablename__ = "staff"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(200), nullable=False)
    initials = Column(String(10))
    role = Column(String(50), server_default="field_staff")  # field_staff | data_processor | admin
    is_active = Column(Boolean, server_default=text("TRUE"))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("CURRENT_TIMESTAMP"))

    observer_links = relationship("LogSheetObserver", back_populates="staff_member")

    def __repr__(self) -> str:
        return f"<Staff {self.full_name} ({self.role})>"


class LogSheetObserver(FieldOpsBase):
    """
    Junction table: which staff members were present for a given logsheet visit.

    A single logsheet can have multiple observers (e.g. lead technician +
    assistant). Deleting a logsheet cascades to remove observer rows; deleting
    a staff record is RESTRICTED if they appear on any logsheet (preserves
    audit trail).
    """

    __tablename__ = "logsheet_observers"
    __table_args__ = {"schema": SCHEMA}

    logsheet_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.logsheets.id", ondelete="CASCADE"),
        primary_key=True,
    )
    staff_id = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.staff.id", ondelete="RESTRICT"),
        primary_key=True,
    )

    logsheet = relationship("LogSheet", back_populates="observers")
    staff_member = relationship("Staff", back_populates="observer_links")


class EquipmentInventory(FieldOpsBase):
    """
    GNSS equipment tracked by QR code.

    Each physical item (receiver, antenna, cable) gets a QR sticker.
    The PWA's QR scanner resolves qr_code → equipment record to pre-fill
    logsheet equipment fields.
    """

    __tablename__ = "equipment_inventory"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    qr_code = Column(Text, unique=True, nullable=False)
    equipment_type = Column(String(100))   # GNSS Receiver | Antenna | Cable | etc.
    serial_number = Column(String(100))
    station_code = Column(String(10))      # current assigned station (loose ref)
    status = Column(String(50), server_default="active")  # active | retired | lost
    last_seen = Column(TIMESTAMP(timezone=True))
    notes = Column(Text)

    def __repr__(self) -> str:
        return f"<Equipment {self.qr_code} ({self.equipment_type})>"


class LogSheetPhoto(FieldOpsBase):
    """Photo attachment for a logsheet (antenna, equipment, site conditions)."""

    __tablename__ = "logsheet_photos"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    logsheet_id = Column(Integer, ForeignKey(f"{SCHEMA}.logsheets.id"), nullable=False)
    filename = Column(Text, nullable=False)
    storage_path = Column(Text)             # local path or R2 key
    # sha256 of the uploaded bytes. Unique per logsheet (partial index,
    # migration 014) so a retry after a lost response returns the existing
    # row instead of storing the same image again.
    content_sha256 = Column(Text)
    taken_at = Column(TIMESTAMP(timezone=True))
    uploaded_at = Column(TIMESTAMP(timezone=True), server_default=text("CURRENT_TIMESTAMP"))

    logsheet = relationship("LogSheet", back_populates="photos")


class EquipmentHistory(FieldOpsBase):
    """
    Temporal (SCD Type 2) record of hardware installed at each station.

    Each row represents one equipment item for the duration it was installed
    (date_installed → date_removed). date_removed IS NULL means currently active.

    Use case: answer "what receiver was at PBIS during the Cotabato earthquake
    on 2019-10-29?" via:
        WHERE station_code = 'PBIS'
          AND date_installed <= '2019-10-29'
          AND (date_removed IS NULL OR date_removed > '2019-10-29')

    arp_height_m and elevation_cutoff_deg feed Bernese .STA file generation —
    this table is the authoritative source for those values.
    """

    __tablename__ = "equipment_history"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_code = Column(String(10), nullable=False)   # loose ref to public.stations

    # Hardware classification
    equipment_type = Column(String(100))    # GNSS Receiver | Antenna | Cable | etc.
    serial_number = Column(String(100))

    # Receiver details
    manufacturer = Column(String(100))
    model = Column(String(100))
    firmware_version = Column(String(50))
    num_channels = Column(Integer)

    # Antenna details
    antenna_manufacturer = Column(String(100))
    antenna_model = Column(String(100))     # e.g. TRM41249.00
    radome_type = Column(String(50))

    # Installation specs (Bernese .STA inputs)
    antenna_location = Column(String(100))  # Rooftop | Ground | Pillar
    cable_length_m = Column(Float)
    elevation_cutoff_deg = Column(Float)
    arp_height_m = Column(Float)            # Antenna Reference Point height above monument

    # Infrastructure
    power_source = Column(String(100))      # Solar | AC-DC | Battery | Solar+Battery
    has_internet = Column(Boolean)
    has_lightning_rod = Column(Boolean)

    # Constellation support
    satellite_systems = Column(Text)        # GPS | GNSS | GPS+GLONASS

    # Valid-time interval
    date_installed = Column(Date)           # NULL = unknown start
    date_removed = Column(Date)             # NULL = currently installed

    notes = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("CURRENT_TIMESTAMP"))

    def __repr__(self) -> str:
        removed = self.date_removed or "present"
        return f"<EquipmentHistory {self.station_code} {self.model} [{self.date_installed}–{removed}]>"


class StationProposal(FieldOpsBase):
    """
    A site an observer created from the handset, awaiting reconciliation.

    FO-001. Design: docs/project_documentation/field_ops_station_creation_design.md

    WHY A SEPARATE TABLE RATHER THAN A FLAG ON public.stations
    -----------------------------------------------------------
    `public.stations` serves VADASE and Bernese as well as this picker, and
    field-ops deliberately reads it through raw SQL rather than importing
    across the service boundary. Keeping proposals here means:

      * "unverified" is structural, not a boolean somebody must remember to
        filter on — a query that forgets the flag cannot leak a proposed site
        into the processing chain;
      * the migration lands in the field-ops alembic tree, not the root one,
        which per DEPLOY.md cannot reach head on Neon;
      * it cannot collide with `seed_network_inventory.py`'s deliberate
        COALESCE upsert.

    `reconciled_at` IS THE STATE MACHINE
    ------------------------------------
    NULL   -> pending
    set + reconciled_station_id  -> promoted
    set + rejected_reason        -> rejected

    One nullable timestamp that also records *when* beats an enum plus a
    separate timestamp. The partial unique index in fo007 keys off
    `reconciled_at IS NULL`, so a code becomes proposable again once an
    earlier proposal is resolved — a plain unique index would permanently
    burn every code ever typed, typos included.

    A rejected row is KEPT. A rejected proposal with sheets already filed
    against it is a data-quality finding, not garbage.

    DEVIATION FROM THE DESIGN, DELIBERATE
    -------------------------------------
    The design specifies a PostGIS POINT for `location`. This stores plain
    `latitude`/`longitude` floats instead, and builds the POINT at promotion
    with the same `ST_SetSRID(ST_MakePoint(lon, lat), 4326)` the seeder uses.

    Reason: the design names testability as "the largest hidden cost" of this
    ticket — there is no Postgres fixture, so nothing PostGIS-touching can be
    tested. Floats keep the entire proposal lifecycle exercisable on the
    existing SQLite conftest and confine PostGIS to the one promotion
    function, which is exactly the "station-lookup seam" the design offers as
    its second option. No information is lost: the picker consumes lat/lon
    floats anyway (`GET /stations` already extracts them with ST_Y/ST_X).
    """

    __tablename__ = "station_proposals"
    __table_args__ = {"schema": SCHEMA}

    id = Column(Integer, primary_key=True)

    # Idempotency key, minted on the handset before going offline. Same
    # contract as logsheets.client_uuid: a retried sync cannot double-insert.
    client_uuid = Column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)

    # VARCHAR(10) to match public.stations.station_code and logsheets.station_code.
    # Canonically 4 characters.
    station_code = Column(String(10), nullable=False, index=True)
    name = Column(String(200))

    # See the deviation note above.
    latitude = Column(Float)
    longitude = Column(Float)
    elevation = Column(Float)

    monitoring_method = Column(String(20), nullable=False, server_default=text("'campaign'"))
    status = Column(String(30), nullable=False, server_default=text("'active'"))

    # Mirrors public.stations so promotion is a straight copy, not a mapping.
    municipality = Column(String(100))
    province = Column(String(100))
    region = Column(String(100))

    created_by = Column(Integer, ForeignKey(f"{SCHEMA}.users.id"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("CURRENT_TIMESTAMP"))

    # Handset time at creation, which may be days earlier than created_at when
    # the proposal was made offline. Both are kept: they answer different
    # questions ("when was the observer at the monument" vs "when did we hear").
    proposed_at = Column(TIMESTAMP(timezone=True))

    reconciled_at = Column(TIMESTAMP(timezone=True))
    reconciled_by = Column(Integer, ForeignKey(f"{SCHEMA}.users.id"))
    reconciled_station_id = Column(Integer)
    rejected_reason = Column(Text)

    notes = Column(Text)

    creator = relationship("User", foreign_keys=[created_by])
    reconciler = relationship("User", foreign_keys=[reconciled_by])

    def __repr__(self) -> str:
        if self.reconciled_at is None:
            state = "pending"
        elif self.reconciled_station_id is not None:
            state = f"promoted->{self.reconciled_station_id}"
        else:
            state = "rejected"
        return f"<StationProposal {self.station_code} [{state}]>"
