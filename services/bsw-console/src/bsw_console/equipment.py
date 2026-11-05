"""The equipment report, read for the station view. Read-only.

`bernese-check-equipment --json` (bernese_workflow.equipment_check) compares a
.STA file's equipment with field-ops' records and writes a JSON report; on
gps3 it runs after the nightly export (scripts/export_field_equipment.py).
The console reads that file, named by BSW_CONSOLE_EQUIPMENT_REPORT, and shows
one station's part of it. It never runs the comparison, never reads the
field-ops database, and never writes anything.

Every answer is 200 with `configured` and, when configured, `available`:
the panel states plainly that there is no report, or that it cannot be read,
rather than failing. The export's time comes from the report, which copied it
from the export file, so a stale export is visible on the page.
"""

from __future__ import annotations

import json
from pathlib import Path

from .settings import Settings

NOT_CONFIGURED = (
    "No equipment report is configured for this console (BSW_CONSOLE_EQUIPMENT_REPORT), "
    "so there is nothing to compare this station's .STA equipment with."
)


def _load(path: Path) -> tuple[dict | None, str]:
    try:
        rep = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"The equipment report {path.name} could not be read: {type(exc).__name__}."
    if not isinstance(rep, dict) or not {"sta", "sources", "current", "visits", "names"} <= set(
        rep
    ):
        return None, f"The equipment report {path.name} could not be read: not a report."
    return rep, ""


def _about(path: Path, rep: dict) -> dict:
    src = rep.get("sources") or {}
    export = src.get("logsheet_export") or {}
    return {
        "configured": True,
        "available": True,
        "written": path.stat().st_mtime,
        "sta": rep.get("sta"),
        "exported_at": export.get("exported_at"),
        "export_counts": export.get("counts"),
        "equipment_csv": (src.get("equipment_csv") or {}).get("path"),
        "current_equipment_from": src.get("current_equipment_from"),
    }


def summary(s: Settings) -> dict:
    if s.equipment_report is None:
        return {"configured": False, "message": NOT_CONFIGURED}
    rep, why = _load(s.equipment_report)
    if rep is None:
        return {"configured": True, "available": False, "message": why}
    return {**_about(s.equipment_report, rep), "summary": rep.get("summary") or {}}


def for_station(s: Settings, code: str) -> dict:
    """One station's entries. ``code`` is already checked as four letters or digits."""
    code = code.upper()
    if s.equipment_report is None:
        return {"configured": False, "station": code, "message": NOT_CONFIGURED}
    rep, why = _load(s.equipment_report)
    if rep is None:
        return {"configured": True, "available": False, "station": code, "message": why}
    pick = lambda key: [e for e in rep.get(key) or [] if e.get("station") == code]  # noqa: E731
    return {
        **_about(s.equipment_report, rep),
        "station": code,
        "current": pick("current"),
        "visits": pick("visits"),
        "names": pick("names"),
    }
