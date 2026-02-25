"""
Seed the stations table from a YAML configuration file.

Idempotent: uses INSERT ... ON CONFLICT (station_code) DO UPDATE so it is safe
to run multiple times — subsequent runs update existing rows with the latest
YAML values rather than failing on the unique constraint.

Usage:
    # Default config (vadase stations.yml)
    uv run python scripts/seed_stations.py

    # Explicit config path
    uv run python scripts/seed_stations.py --config path/to/stations.yml

    # Dry run (print what would be inserted without touching the DB)
    uv run python scripts/seed_stations.py --dry-run

Environment variables (with docker-compose.yml defaults):
    POGF_DB_USER      pogf_user
    POGF_DB_PASSWORD  pogf_password
    POGF_DB_HOST      localhost
    POGF_DB_PORT      5433
    POGF_DB_NAME      pogf_db
"""

import os
import sys
from pathlib import Path

# Make src.db.models importable when run from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse

import yaml
from geoalchemy2 import WKTElement
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.db.models import Base, Station


def get_db_url() -> str:
    return (
        "postgresql://"
        f"{os.getenv('POGF_DB_USER', 'pogf_user')}:"
        f"{os.getenv('POGF_DB_PASSWORD', 'pogf_password')}@"
        f"{os.getenv('POGF_DB_HOST', 'localhost')}:"
        f"{os.getenv('POGF_DB_PORT', '5433')}/"
        f"{os.getenv('POGF_DB_NAME', 'pogf_db')}"
    )


def load_stations_yaml(config_path: Path) -> list[dict]:
    with open(config_path) as f:
        config = yaml.safe_load(f)
    stations = config.get("stations", [])
    if not stations:
        raise ValueError(f"No 'stations' key found in {config_path}")
    return stations


def seed(config_path: Path, dry_run: bool = False) -> None:
    stations_data = load_stations_yaml(config_path)

    print(f"Loaded {len(stations_data)} station(s) from {config_path}")

    if dry_run:
        print("\n[DRY RUN] Would upsert:")
        for s in stations_data:
            print(f"  {s['id']:6s}  {s.get('name', '(no name)')}")
        return

    engine = create_engine(get_db_url(), echo=False)

    with Session(engine) as session:
        upserted = 0
        for s in stations_data:
            lat = s.get("latitude")
            lon = s.get("longitude")
            location = (
                WKTElement(f"POINT({lon} {lat})", srid=4326)
                if lat is not None and lon is not None
                else None
            )
            stmt = (
                pg_insert(Station)
                .values(
                    station_code=s["id"],
                    name=s.get("name"),
                    location=location,
                    elevation=s.get("elevation"),
                    host=s.get("host"),
                    port=s.get("port"),
                    fault_segment=s.get("fault_segment"),
                    status="active",
                    agency="PHIVOLCS",
                )
                .on_conflict_do_update(
                    constraint="uq_stations_station_code",
                    set_={
                        "name": s.get("name"),
                        "location": location,
                        "elevation": s.get("elevation"),
                        "host": s.get("host"),
                        "port": s.get("port"),
                        "fault_segment": s.get("fault_segment"),
                    },
                )
            )
            session.execute(stmt)
            upserted += 1

        session.commit()

    print(f"Upserted {upserted} station(s) into the database.")

    # Verify
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT station_code, name, "
                "ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon "
                "FROM stations ORDER BY station_code"
            )
        )
        rows = result.fetchall()
        print(f"\nCurrent stations table ({len(rows)} rows):")
        for row in rows:
            lat_str = f"{row.lat:.4f}" if row.lat is not None else "N/A"
            lon_str = f"{row.lon:.4f}" if row.lon is not None else "N/A"
            print(f"  {row.station_code:6s}  {row.name or '':40s}  {lat_str}, {lon_str}")


def main() -> None:
    default_config = (
        Path(__file__).parent.parent
        / "services/vadase-rt-monitor/config/stations.yml"
    )

    parser = argparse.ArgumentParser(description="Seed the stations table from YAML.")
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config,
        help=f"Path to stations YAML file (default: {default_config})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be inserted without touching the database",
    )
    args = parser.parse_args()

    if not args.config.exists():
        print(f"Error: config file not found: {args.config}", file=sys.stderr)
        sys.exit(1)

    seed(args.config, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
