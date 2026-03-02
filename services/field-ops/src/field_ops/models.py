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
    plumbing_offset_mm = Column(Float)

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
    storage_path = Column(Text)             # local path or future S3 key
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
