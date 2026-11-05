#!/usr/bin/env python3
"""
Export field-ops equipment records to one JSON file, read-only.

    uv run python scripts/export_field_equipment.py --out /path/to/field_equipment.json

WHY A FILE AND NOT A LIVE QUERY
`bernese-check-equipment` compares a .STA file with what field-ops records
(docs/project_documentation/field_ops_sta_reconciliation_design.md, decision
2). gps3's outbound access times out at times, and a check that needs the
hosted database would fail exactly when someone wants it. So this exports
once, nightly, and the report reads the file. The file carries `exported_at`,
which the report prints, so stale data is visible rather than silent.

WHAT IT WRITES
{
  "format": "field-ops-equipment-export", "version": 1,
  "exported_at": "<UTC, ISO 8601>",
  "counts": {"logsheets": N, "equipment_history": M},
  "logsheets": [...],          LOGSHEET_COLUMNS: the visit, equipment_changed
                               and every *_before/*_after equipment column
  "equipment_history": [...]   HISTORY_COLUMNS: every column of the table
}
Logsheet notes, weather, observers and the submitting user are not exported:
the report needs equipment, and the file should not carry more than that.
Every exported logsheet column comes from field-ops' own migrations (the
before/after block is fo004), not from the repo-root tree, so the export works
on a database migrated by either.

READ-ONLY, TWICE
Every query runs in one transaction opened with
`SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY`, and the
transaction is rolled back, never committed. REPEATABLE READ makes the two
tables one snapshot, so the counts agree with each other. The second guard is
the database role: run this as a role that can only SELECT those two tables
(the PR that added this script carries the SQL for one). Either guard alone
would stop a write; together, a bug here cannot touch field-ops.

DATABASE
DATABASE_URL, else the POGF_DB_* variables: the same resolution as
scripts/seed_network_inventory.py, imported from it so there is one copy. The
URL is never printed.

RUNNING IT NIGHTLY ON gps3
Nothing installs this. To run it from cron, as the account that runs the
report, with the read-only role's URL in a file only that account can read:

    # m h dom mon dow  command
    41 1 * * *  cd $HOME/movefaults && set -a && . $HOME/.config/field_ops_export.env \
        && set +a && uv run python scripts/export_field_equipment.py \
        --out $HOME/.local/state/bernese-workflow/field_equipment.json \
        >> $HOME/.local/state/bernese-workflow/field_equipment.log 2>&1

The write is atomic (temporary file, then rename), so a report run during the
export reads the previous file whole. Exit 0 on success, 2 when the database
cannot be reached or read; the previous file is then left as it was.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import tempfile
import uuid
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seed_network_inventory import database_url  # noqa: E402 -- one resolution, shared

EXPORT_FORMAT = "field-ops-equipment-export"
EXPORT_VERSION = 1
READ_ONLY = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"

LOGSHEET_COLUMNS = (
    "id",
    "client_uuid",
    "station_code",
    "visit_date",
    "arrival_time",
    "departure_time",
    "equipment_changed",
    "receiver_model_before",
    "receiver_model_after",
    "receiver_serial_before",
    "receiver_serial_after",
    "receiver_firmware_before",
    "receiver_firmware_after",
    "antenna_type_before",
    "antenna_type_after",
    "antenna_part_number_before",
    "antenna_part_number_after",
    "antenna_serial_before",
    "antenna_serial_after",
    "antenna_height_before_m",
    "antenna_height_after_m",
)
HISTORY_COLUMNS = (
    "id",
    "station_code",
    "equipment_type",
    "serial_number",
    "manufacturer",
    "model",
    "firmware_version",
    "num_channels",
    "antenna_manufacturer",
    "antenna_model",
    "radome_type",
    "antenna_location",
    "cable_length_m",
    "elevation_cutoff_deg",
    "arp_height_m",
    "power_source",
    "has_internet",
    "has_lightning_rod",
    "satellite_systems",
    "date_installed",
    "date_removed",
    "notes",
    "created_at",
)
QUERIES = {
    "logsheets": (
        f"SELECT {', '.join(LOGSHEET_COLUMNS)} FROM field_ops.logsheets ORDER BY visit_date, id",
        LOGSHEET_COLUMNS,
    ),
    "equipment_history": (
        f"SELECT {', '.join(HISTORY_COLUMNS)} FROM field_ops.equipment_history "
        "ORDER BY station_code, id",
        HISTORY_COLUMNS,
    ),
}


def _plain(value: object) -> object:
    if isinstance(value, dt.datetime | dt.date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    return value


def export(conn, now: dt.datetime | None = None) -> dict:
    """Both tables, in one read-only transaction that is rolled back, never committed."""
    conn.autocommit = False
    conn.rollback()  # start clean: SET TRANSACTION must be the transaction's first statement
    exported_at = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC).isoformat(timespec="seconds")
    doc: dict = {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "exported_at": exported_at,
        "counts": {},
    }
    try:
        cur = conn.cursor()
        cur.execute(READ_ONLY)
        for key, (sql, columns) in QUERIES.items():
            cur.execute(sql)
            doc[key] = [
                {c: _plain(v) for c, v in zip(columns, row, strict=True)} for row in cur.fetchall()
            ]
            doc["counts"][key] = len(doc[key])
    finally:
        conn.rollback()
    return doc


def write_atomic(doc: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{out.name}.", dir=out.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=1)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, out)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Export field-ops equipment records, read-only.")
    ap.add_argument("--out", type=Path, required=True, help="the JSON file to write")
    args = ap.parse_args(argv)

    import psycopg2

    try:
        conn = psycopg2.connect(database_url())
    except psycopg2.Error as exc:
        # The message names the host, never the password; the URL itself is not printed.
        print(f"cannot connect: {type(exc).__name__}: {str(exc).strip()}", file=sys.stderr)
        return 2
    try:
        doc = export(conn)
    except psycopg2.Error as exc:
        print(f"cannot read: {type(exc).__name__}: {str(exc).strip()}", file=sys.stderr)
        return 2
    finally:
        conn.close()
    write_atomic(doc, args.out)
    counts = ", ".join(f"{v} {k}" for k, v in doc["counts"].items())
    print(f"exported {counts} at {doc['exported_at']} to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
