"""
Central POGF database models (SQLAlchemy ORM).

These models define the authoritative schema for the centralized geodetic
database (Deliverable 1.1). Alembic reads this metadata to validate migrations.

Tables managed here:
  - stations       : CORS station inventory (shared by VADASE, Bernese, ingestion)
  - rinex_files    : Catalogue of ingested RINEX observation files

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
from sqlalchemy.dialects.postgresql import JSONB
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
