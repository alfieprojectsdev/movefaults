#!/usr/bin/env python3
"""
Seed public.stations and field_ops.equipment_history from the committed CSVs.

    uv run python scripts/seed_network_inventory.py --dry-run
    uv run python scripts/seed_network_inventory.py

Reads DATABASE_URL, falling back to the POGF_DB_* variables — the same
resolution the application and both alembic trees use, so "which database did
that write to?" has one answer everywhere.

Idempotent. Stations upsert on `station_code`; equipment rows are keyed on
(station_code, model, antenna_model, date_installed), which is what identifies
one installation in a sheet with no serial numbers. Re-running after the sheet
is re-exported updates in place rather than accumulating duplicates.

What this does NOT populate, and why it matters
-----------------------------------------------
**field_ops.equipment_inventory is untouched.** That table is what the PWA's QR
scanner resolves, and its `qr_code` is NOT NULL UNIQUE. The sheet has no QR
codes and no serial numbers, so there is nothing to key a row on — inventing
identifiers would produce stickers matching nothing physical. Equipment lookup
in the field app stays unseeded until real QR codes exist.

**cable_length_m, elevation_cutoff_deg and arp_height_m stay NULL.** The sheet's
`antenna_cable_length` column holds prose about which floor the receiver sits on
(0 of 117 values are numeric), and the elevation-cutoff column is empty for
every row. The latter two are Bernese .STA inputs; this seed cannot supply them
and does not pretend to.

**Staff carry names only.** field_ops.staff holds full_name, initials, role and
is_active — nothing else. The source notes for those people also contain salary,
salary grade, birthday, cellphone number, personal email, passport number,
national ID and bank details; none of it is extracted, none of it is in the CSV,
and none of it belongs in this repository, which is public. If the app ever
needs to contact an observer, that is a lookup against an internal system, not a
column here.

**No campaign sites.** All 135 rows are continuous CORS. Campaign occupations —
including the Palawan sites — are not in this spreadsheet and must be seeded
from another source.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "network_inventory"


def database_url() -> str:
    """DATABASE_URL first, then the discrete fields — as the app resolves it."""
    if explicit := os.getenv("DATABASE_URL", "").strip():
        return explicit.replace("postgresql+asyncpg://", "postgresql://", 1)
    return (
        f"postgresql://{os.getenv('POGF_DB_USER', 'pogf_user')}:"
        f"{os.getenv('POGF_DB_PASSWORD', 'pogf_password')}@"
        f"{os.getenv('POGF_DB_HOST', 'localhost')}:"
        f"{os.getenv('POGF_DB_PORT', '5433')}/"
        f"{os.getenv('POGF_DB_NAME', 'pogf_db')}"
    )


def read_csv(name: str) -> list[dict]:
    path = DATA_DIR / name
    if not path.exists():
        raise SystemExit(
            f"{path} not found — run scripts/extract_network_inventory.py first."
        )
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# staff.csv is hand-edited — it is where someone corrects a role — and neither
# the database nor the app validates this field: there is no CHECK constraint,
# and the observer picker renders whatever string it is given. So a typo like
# "data_processer" would be written, shown in the dropdown, and never reported.
# Checked here because this is the last point that can refuse it.
VALID_ROLES = {"field_staff", "data_processor", "admin"}


def validate_staff(rows: list[dict]) -> None:
    problems = []
    for row in rows:
        role = (row.get("role") or "").strip()
        if role and role not in VALID_ROLES:
            problems.append(f"  {row.get('initials', '?')}: unknown role {role!r}")
    if problems:
        raise SystemExit(
            "staff.csv has roles this app does not understand:\n"
            + "\n".join(problems)
            + f"\n\nValid roles: {', '.join(sorted(VALID_ROLES))}\n"
            "Nothing was written — fix the file and re-run."
        )


def nullable(value: str | None):
    """Empty CSV cell -> SQL NULL, so 'unknown' never lands as an empty string."""
    v = (value or "").strip()
    return v or None


def as_float(value: str | None):
    v = (value or "").strip()
    return float(v) if v else None


def as_int(value: str | None):
    v = (value or "").strip()
    return int(v) if v else None


def as_bool(value: str | None):
    v = (value or "").strip().lower()
    return True if v == "true" else False if v == "false" else None


STATION_SQL = """
INSERT INTO public.stations (
    station_code, name, location, agency, status, date_installed,
    monitoring_method, municipality, province, region, land_owner,
    maintenance_interval_days, metadata_json
) VALUES (
    %(station_code)s, %(name)s,
    CASE WHEN %(longitude)s IS NULL OR %(latitude)s IS NULL THEN NULL
         ELSE ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), 4326) END,
    %(agency)s, COALESCE(%(status)s, 'active'), %(date_installed)s,
    %(monitoring_method)s, %(municipality)s, %(province)s, %(region)s,
    %(land_owner)s, %(maintenance_interval_days)s, %(metadata_json)s
)
ON CONFLICT (station_code) DO UPDATE SET
    name              = COALESCE(EXCLUDED.name, public.stations.name),
    location          = COALESCE(EXCLUDED.location, public.stations.location),
    agency            = COALESCE(EXCLUDED.agency, public.stations.agency),
    status            = EXCLUDED.status,
    date_installed    = COALESCE(EXCLUDED.date_installed, public.stations.date_installed),
    monitoring_method = EXCLUDED.monitoring_method,
    municipality      = COALESCE(EXCLUDED.municipality, public.stations.municipality),
    province          = COALESCE(EXCLUDED.province, public.stations.province),
    region            = COALESCE(EXCLUDED.region, public.stations.region),
    land_owner        = COALESCE(EXCLUDED.land_owner, public.stations.land_owner),
    maintenance_interval_days = COALESCE(
        EXCLUDED.maintenance_interval_days, public.stations.maintenance_interval_days),
    metadata_json     = COALESCE(EXCLUDED.metadata_json, public.stations.metadata_json)
"""

# COALESCE on update, not blind assignment: a later hand-correction in the
# database (a coordinate fixed after a site visit) must not be reverted to NULL
# by re-running the seed from a sheet that never had the value.

STAFF_SQL = """
INSERT INTO field_ops.staff (full_name, initials, role, is_active)
VALUES (%(full_name)s, %(initials)s, %(role)s, %(is_active)s)
ON CONFLICT DO NOTHING
"""

STAFF_UPDATE_SQL = """
UPDATE field_ops.staff
   SET role = %(role)s, is_active = %(is_active)s, initials = %(initials)s
 WHERE full_name = %(full_name)s
   AND (role IS DISTINCT FROM %(role)s
        OR is_active IS DISTINCT FROM %(is_active)s
        OR initials IS DISTINCT FROM %(initials)s)
"""

EQUIP_FIND_SQL = """
SELECT id FROM field_ops.equipment_history
WHERE station_code = %s
  AND model IS NOT DISTINCT FROM %s
  AND antenna_model IS NOT DISTINCT FROM %s
  AND date_installed IS NOT DISTINCT FROM %s
"""

EQUIP_INSERT_SQL = """
INSERT INTO field_ops.equipment_history (
    station_code, equipment_type, manufacturer, model, num_channels,
    antenna_manufacturer, antenna_model, radome_type, antenna_location,
    power_source, has_internet, has_lightning_rod,
    date_installed, date_removed, notes
) VALUES (
    %(station_code)s, 'GNSS Receiver', %(manufacturer)s, %(model)s, %(num_channels)s,
    %(antenna_manufacturer)s, %(antenna_model)s, %(radome_type)s, %(antenna_location)s,
    %(power_source)s, %(has_internet)s, %(has_lightning_rod)s,
    %(date_installed)s, %(date_removed)s, %(notes)s
)
"""

EQUIP_UPDATE_SQL = """
UPDATE field_ops.equipment_history SET
    manufacturer = %(manufacturer)s, num_channels = %(num_channels)s,
    antenna_manufacturer = %(antenna_manufacturer)s, radome_type = %(radome_type)s,
    antenna_location = %(antenna_location)s, power_source = %(power_source)s,
    has_internet = %(has_internet)s, has_lightning_rod = %(has_lightning_rod)s,
    date_removed = %(date_removed)s, notes = %(notes)s
WHERE id = %(id)s
"""


def station_params(row: dict) -> dict:
    # "Twice per year" is the only cadence in the sheet. Stored as an interval
    # in days because that is what the column holds; 182 rather than 183 so a
    # due-date calculation errs towards visiting early.
    interval = 182 if "twice" in (row.get("period_constructed_raw") or "").lower() else None
    extra = {
        k: row[k]
        for k in ("project", "collaborator", "last_visit", "date_decommissioned",
                  "period_constructed_raw")
        if row.get(k)
    }
    extra["sheet"] = "Inventory/SiteMetaData 1Y8TTzf…EFxVA"
    # The sheet's `network` column ("NCKU Leyte", "IESAS Luzon", "VFS Single
    # Frequency") is a sub-network grouping, not an owning agency — several are
    # the Taiwanese institutions collaborating under the RP-Taiwan Project.
    # Writing it to `agency` made ABUY read as owned by "NCKU Leyte", when the
    # site is in PHIVOLCS's own inventory. It belongs here; `agency` keeps its
    # PHIVOLCS default for inventory rows and is set only for NAMRIA's.
    if net := nullable(row.get("network")):
        extra["network"] = net
    # Which block of the sheet the row came from. `namria_pagenet_list` rows
    # are another agency's sites with coordinates but no verified status —
    # worth keeping distinguishable once they are in the same table as ours.
    extra["source"] = row.get("source") or "unknown"
    return {
        "station_code": row["station_code"],
        "name": nullable(row["name"]),
        "latitude": as_float(row["latitude"]),
        "longitude": as_float(row["longitude"]),
        # NULL rather than "" lets the column default to PHIVOLCS; the NAMRIA
        # rows carry their owner explicitly so they are not mistaken for ours.
        "agency": nullable(row["agency"]),
        "status": nullable(row["status"]),
        "date_installed": nullable(row["date_installed"]),
        "monitoring_method": nullable(row["monitoring_method"]) or "continuous",
        "municipality": nullable(row["municipality"]),
        "province": nullable(row["province"]),
        "region": nullable(row["region"]),
        "land_owner": nullable(row["land_owner"]),
        "maintenance_interval_days": interval,
        "metadata_json": psycopg2.extras.Json(extra) if extra else None,
    }


def equip_params(row: dict) -> dict:
    notes = row.get("housing_notes") or ""
    if as_bool(row.get("vadase")):
        notes = ("VADASE stream. " + notes).strip()
    return {
        "station_code": row["station_code"],
        "manufacturer": nullable(row["manufacturer"]),
        "model": nullable(row["model"]),
        "num_channels": as_int(row["num_channels"]),
        "antenna_manufacturer": nullable(row["antenna_manufacturer"]),
        "antenna_model": nullable(row["antenna_model"]),
        "radome_type": nullable(row["radome_type"]),
        "antenna_location": nullable(row["antenna_location"]),
        "power_source": nullable(row["power_source"]),
        "has_internet": as_bool(row["has_internet"]),
        "has_lightning_rod": as_bool(row["has_lightning_rod"]),
        "date_installed": nullable(row["date_installed"]),
        "date_removed": nullable(row["date_removed"]),
        "notes": nullable(notes),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change, then roll back without committing.",
    )
    args = ap.parse_args()

    stations = read_csv("stations.csv")
    equipment = read_csv("equipment.csv")
    staff = read_csv("staff.csv")
    validate_staff(staff)

    url = database_url()
    # Never print the URL — it carries the password. Host and database only.
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    print(f"target: {parts.hostname}:{parts.port or 5432}{parts.path}")
    print(
        f"source: {len(stations)} stations, {len(equipment)} equipment rows, "
        f"{len(staff)} staff"
    )

    conn = psycopg2.connect(url)
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.stations")
            before_st = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM field_ops.equipment_history")
            before_eq = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM field_ops.staff")
            before_staff = cur.fetchone()[0]

            # Staff are matched on full_name so a re-run cannot duplicate them.
            # No ON CONFLICT target exists (the table has no unique constraint
            # on the name), so the check is explicit rather than clever.
            #
            # Existing rows are UPDATED, not skipped. staff.csv is hand-edited —
            # it is where someone corrects a role — and a seeder that only ever
            # inserts turns that edit into a no-op: the file says one thing, the
            # database another, and nothing reports the divergence. The columns
            # rewritten here are all reference data sourced from the CSV.
            staff_added = staff_changed = 0
            for row in staff:
                params = {
                    "full_name": row["full_name"],
                    "initials": nullable(row["initials"]),
                    "role": nullable(row["role"]) or "field_staff",
                    "is_active": as_bool(row["is_active"]) is not False,
                }
                cur.execute(
                    "SELECT 1 FROM field_ops.staff WHERE full_name = %s",
                    (row["full_name"],),
                )
                if cur.fetchone():
                    cur.execute(STAFF_UPDATE_SQL, params)
                    staff_changed += cur.rowcount
                else:
                    cur.execute(STAFF_SQL, params)
                    staff_added += 1

            for row in stations:
                cur.execute(STATION_SQL, station_params(row))

            inserted = updated = 0
            for row in equipment:
                p = equip_params(row)
                cur.execute(
                    EQUIP_FIND_SQL,
                    (p["station_code"], p["model"], p["antenna_model"], p["date_installed"]),
                )
                found = cur.fetchone()
                if found:
                    cur.execute(EQUIP_UPDATE_SQL, {**p, "id": found[0]})
                    updated += 1
                else:
                    cur.execute(EQUIP_INSERT_SQL, p)
                    inserted += 1

            cur.execute("SELECT COUNT(*) FROM public.stations")
            after_st = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(*) FROM public.stations WHERE location IS NOT NULL"
            )
            with_loc = cur.fetchone()[0]

            print(f"stations:  {before_st} -> {after_st} ({with_loc} with a location)")
            cur.execute("SELECT COUNT(*) FROM field_ops.staff")
            after_staff = cur.fetchone()[0]

            print(f"equipment: {before_eq} -> {before_eq + inserted} "
                  f"({inserted} inserted, {updated} updated)")
            print(
                f"staff:     {before_staff} -> {after_staff} "
                f"({staff_added} added, {staff_changed} updated)"
            )

            if args.dry_run:
                conn.rollback()
                print("\ndry run — rolled back, nothing written")
                return
        print("\ncommitted")
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
