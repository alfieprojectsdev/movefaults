-- TimescaleDB schema initialization for VADASE monitoring
-- Run this script after creating the database

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Velocity measurements (LVM data)
CREATE TABLE vadase_velocity (
    time TIMESTAMPTZ NOT NULL,
    station TEXT NOT NULL,
    vE DOUBLE PRECISION,          -- m/s (East)
    vN DOUBLE PRECISION,          -- m/s (North)
    vU DOUBLE PRECISION,          -- m/s (Up)
    varE DOUBLE PRECISION,        -- m²/s²
    varN DOUBLE PRECISION,        -- m²/s²
    varU DOUBLE PRECISION,        -- m²/s²
    covEN DOUBLE PRECISION,       -- m²/s²
    covEU DOUBLE PRECISION,       -- m²/s²
    covUN DOUBLE PRECISION,       -- m²/s²
    cq DOUBLE PRECISION,          -- m/s (3D quality)
    n_sats INTEGER,
    vH_magnitude DOUBLE PRECISION, -- Computed horizontal magnitude (m/s)
    PRIMARY KEY (time, station)
);

-- Convert to hypertable
SELECT create_hypertable('vadase_velocity', 'time');

-- Displacement measurements (LDM data)
CREATE TABLE vadase_displacement (
    time TIMESTAMPTZ NOT NULL,
    station TEXT NOT NULL,
    start_time TIMESTAMPTZ,       -- When displacement computation started
    dE DOUBLE PRECISION,          -- m (East)
    dN DOUBLE PRECISION,          -- m (North)
    dU DOUBLE PRECISION,          -- m (Up)
    varE DOUBLE PRECISION,        -- m²
    varN DOUBLE PRECISION,        -- m²
    varU DOUBLE PRECISION,        -- m²
    covEN DOUBLE PRECISION,       -- m²
    covEU DOUBLE PRECISION,       -- m²
    covUN DOUBLE PRECISION,       -- m²
    cq DOUBLE PRECISION,          -- m (3D quality)
    n_sats INTEGER,
    reset_indicator INTEGER,      -- 0=stream enable, 1=ref pos change
    epoch_completeness DOUBLE PRECISION,   -- 0-1
    overall_completeness DOUBLE PRECISION, -- 0-1
    dH_magnitude DOUBLE PRECISION, -- Computed horizontal magnitude (m)
    PRIMARY KEY (time, station)
);

SELECT create_hypertable('vadase_displacement', 'time');

-- Station metadata is managed by Alembic migrations.
-- Run from the repo root: uv run alembic upgrade head
-- Then seed: uv run python scripts/seed_stations.py
--
-- The canonical stations table (with station_code, lat/lon, host, port, etc.)
-- is defined in migrations/versions/001_create_stations.py and
-- modelled in src/db/models.py.
--
-- VADASE tables (vadase_velocity, vadase_displacement) store station_code
-- as a denormalized TEXT field for write performance — no FK to stations.id.
-- This is intentional: 35+ stations at 1 Hz would pay a FK lookup on every
-- insert at the hot path.

-- Event catalog (earthquake/seismic events)
CREATE TABLE events (
    event_id SERIAL PRIMARY KEY,
    origin_time TIMESTAMPTZ NOT NULL,
    magnitude DOUBLE PRECISION,
    depth_km DOUBLE PRECISION,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    location TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Event detections (VADASE threshold crossings)
CREATE TABLE event_detections (
    detection_id SERIAL,
    station TEXT NOT NULL,
    detection_time TIMESTAMPTZ NOT NULL,
    peak_velocity_horizontal DOUBLE PRECISION,  -- mm/s
    peak_displacement_horizontal DOUBLE PRECISION, -- mm
    duration_seconds DOUBLE PRECISION,
    event_id INTEGER REFERENCES events(event_id),
    PRIMARY KEY (detection_id, detection_time)
);

SELECT create_hypertable('event_detections', 'detection_time');

-- Indexes for fast queries
CREATE INDEX idx_velocity_station_time ON vadase_velocity (station, time DESC);
CREATE INDEX idx_displacement_station_time ON vadase_displacement (station, time DESC);
CREATE INDEX idx_event_detections_station ON event_detections (station, detection_time DESC);

-- Comments for documentation
COMMENT ON TABLE vadase_velocity IS 'Real-time velocity measurements from VADASE LVM sentences';
COMMENT ON TABLE vadase_displacement IS 'Real-time displacement measurements from VADASE LDM sentences';
COMMENT ON TABLE event_detections IS 'Automatic detections when velocity exceeds configured threshold';