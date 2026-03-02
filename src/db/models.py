"""
Central POGF database models (SQLAlchemy ORM).

These models define the authoritative schema for the centralized geodetic
database (Deliverable 1.1). Alembic reads this metadata to validate migrations.

Tables managed here:
  - stations       : CORS station inventory (shared by VADASE, Bernese, ingestion)
  - rinex_files    : Catalogue of ingested RINEX observation files
  - offset_events  : Co-seismic and equipment-change epochs for the velocity pipeline

Tables managed in raw SQL migrations (003_create_timeseries.py):
  - timeseries_data   : TimescaleDB hypertable (processed coordinates from Bernese)
  - velocity_products : Estimated interseismic velocities per station

Note on geometry:
  location uses PostGIS GEOMETRY(Point, 4326) — WGS84 geographic coordinates.
  Requires the PostGIS extension (enabled in migration 001) and geoalchemy2.
  VADASE's hot-path tables store station_code as denormalized TEXT (no spatial
  queries needed there), so the PostGIS overhead is isolated to this table.
"""

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    TIMESTAMP,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import INT4RANGE
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Station(Base):
    """
    CORS station inventory.

    Serves three consumers:
      1. VADASE-rt-monitor — host/port for TCP NMEA stream; location for spatial context
      2. Bernese workflow   — station_code links to .STA info; coordinates for datum
      3. Field Ops PWA      — station_code/name for field log sheet station picker

    station_code is the canonical 4-character CORS identifier (e.g. "PBIS").
    VADASE tables store this value as a denormalized TEXT field for write performance;
    this table is the master record.
    """

    __tablename__ = "stations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_code = Column(String(10), nullable=False)
    name = Column(String(255))
    location = Column(Geometry("POINT", srid=4326))
    elevation = Column(Float)
    agency = Column(String(50), server_default="PHIVOLCS")
    status = Column(String(50), server_default="active")  # active | maintenance | offline
    date_installed = Column(Date)
    fault_segment = Column(Text)
    # VADASE TCP connection fields
    host = Column(Text)
    port = Column(Integer)
    # Administrative location (separate columns for indexed regional reporting)
    municipality = Column(Text)
    province = Column(Text)
    region = Column(Text)
    # Operational metadata
    monitoring_method = Column(String(20), server_default="continuous")  # continuous | campaign
    land_owner = Column(Text)
    maintenance_interval_days = Column(Integer)
    # Queryable JSON for receiver type, antenna type, etc.
    metadata_json = Column(JSONB)
    date_added = Column(TIMESTAMP(timezone=True), server_default=text("now()"))

    __table_args__ = (UniqueConstraint("station_code", name="uq_stations_station_code"),)

    rinex_files = relationship("RinexFile", back_populates="station")

    def __repr__(self) -> str:
        return f"<Station {self.station_code} ({self.name})>"


class RinexFile(Base):
    """
    Catalogue of RINEX observation files ingested into the system.

    Each row represents one RINEX file (typically 24 h, 30 s sampling).
    hash_md5 prevents re-ingestion of duplicate files from different source paths.
    """

    __tablename__ = "rinex_files"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=False)
    filepath = Column(String(1024), nullable=False, unique=True)
    start_time = Column(TIMESTAMP(timezone=True), nullable=False)
    end_time = Column(TIMESTAMP(timezone=True), nullable=False)
    sampling_interval = Column(Float)       # seconds
    receiver_type = Column(String(100))
    antenna_type = Column(String(100))
    hash_md5 = Column(String(32))
    date_added = Column(TIMESTAMP(timezone=True), server_default=text("now()"))

    station = relationship("Station", back_populates="rinex_files")

    def __repr__(self) -> str:
        return f"<RinexFile {self.filepath}>"


class ProcessingStatus(Base):
    """
    Year-by-year Bernese data processing status per station.

    Mirrors the BERN52 Inventory spreadsheet. The Bernese orchestrator
    (Phase 1B-iii) uses this as its job queue — querying pending rows
    before launching a BPE run, then upserting status as work progresses.

    available_days stores non-contiguous Julian day ranges as a PostgreSQL
    int4range array. Example: '{[1,37],[141,365]}' means days 1–37 and
    141–365 have RINEX data present.

    Containment query (is day 200 available?):
        WHERE '[200,200]'::int4range <@ ANY(available_days)
    """

    __tablename__ = "processing_status"
    __table_args__ = (UniqueConstraint("station_code", "processing_year",
                                       name="uq_processing_status"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_code = Column(String(10), nullable=False)   # loose ref to public.stations
    processing_year = Column(Integer, nullable=False)

    status = Column(String(50), nullable=False, server_default="pending")
    # valid values: pending | retrieving | processing | data_complete

    available_days = Column(ARRAY(INT4RANGE))   # e.g. {[1,37],[141,365]}
    staff_assigned = Column(Text)
    notes = Column(Text)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("now()"))

    def __repr__(self) -> str:
        return f"<ProcessingStatus {self.station_code} {self.processing_year} [{self.status}]>"


class OffsetEvent(Base):
    """
    Co-seismic and equipment-change offset epochs for the velocity pipeline.

    Replaces the manual flat `offsets` text file maintained in PLOTS/.
    The Bernese orchestrator materializes this table to an `offsets` file
    before invoking vel_line_v8.m. MATLAB reads the file; this table is
    the source of truth.

    event_type vocabulary matches the PHIVOLCS offsets file convention:
      EQ — co-seismic step (earthquake)
      VE — volcanic event
      CE — calibration or equipment change (antenna swap, monument reset)
      UK — unknown / unclassified

    event_date is stored as DATE. The decimal year written to the offsets
    file is computed at materialisation time:
        decimal_year = year + (day_of_year - 1) / days_in_year
    """

    __tablename__ = "offset_events"
    __table_args__ = (
        UniqueConstraint("station_code", "event_date", "event_type",
                         name="uq_offset_events"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_code = Column(String(10), nullable=False)   # loose ref to public.stations
    event_date = Column(Date, nullable=False)
    event_type = Column(String(10), nullable=False, server_default="UK")
    # valid values: EQ | VE | CE | UK
    description = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("now()"))

    def __repr__(self) -> str:
        return f"<OffsetEvent {self.station_code} {self.event_date} [{self.event_type}]>"
