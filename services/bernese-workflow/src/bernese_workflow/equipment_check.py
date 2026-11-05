"""Compare a .STA file's equipment with what field-ops records. Read-only, advisory.

WHY THIS EXISTS
Every station-information file Bernese reads is edited by hand, and nothing
compared it with field-ops' records of what is physically on the monument. On
gps3 on 2026-11-05 the latest PHNAT.STA rows disagreed with the network
inventory sheet for 43 of 103 antennas and 22 of 103 receivers, some by naming
only (`Leica AR20` for `LEIAR20`) and some by different equipment. A wrong
antenna in the .STA means wrong phase-centre corrections; a wrong one in the
sheet means a field team carries the wrong part. The comparison cannot say
which side is right, only list where they disagree, for a person.
Design: docs/project_documentation/field_ops_sta_reconciliation_design.md,
stage 1.

WHAT IT CHECKS
  current   each station's latest TYPE 002 row (by FROM) against the equipment
            source: the network inventory CSV, or the equipment_history rows
            of a logsheet export. Receiver, antenna model and radome are
            compared separately: the .STA antenna field is MODEL(16)+RADOME(4).
  visits    per logsheet in an export: the row valid at the visit time against
            *_before; and when equipment_changed, a row starting at or after the
            visit's date with the *_after equipment.
  names     each 4-character code in the sources against the .STA's 16-column
            names: none, or more than one.

HOW A FIELD IS JUDGED
  equal                 the source's text is the .STA's, as written
  equal after name map  config/bernese/equipment_names.yaml maps it to the .STA's
  different             the map knows the source's name and it is another one
  unmapped name         not equal, and the map does not know it: never guessed
A station takes the worst of its fields (different, then unmapped, then equal
after name map, then equal); a code on one side only is "only in STA" or "only
in source".

WHAT IT DOES NOT DO
Write anything, anywhere, or block a run. The CLI exits 0 whatever it finds;
2 only when an input cannot be read. The .STA's TYPE 002 rows come from
rinex_header_validator.sta_type002_rows, the package's one reader of them.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from .rinex_header_validator import StaRow, sta_row_dates_usable, sta_type002_rows
from .station_files import read_text, sta_names

DEFAULT_NAME_MAP = (
    Path(__file__).resolve().parents[4] / "config" / "bernese" / "equipment_names.yaml"
)
EXPORT_FORMAT = "field-ops-equipment-export"
KINDS = ("receiver", "antenna", "radome")

EQUAL = "equal"
EQUAL_AFTER_MAP = "equal after name map"
DIFFERENT = "different"
UNMAPPED = "unmapped name"
ONLY_IN_STA = "only in STA"
ONLY_IN_SOURCE = "only in source"
CATEGORIES = (EQUAL, EQUAL_AFTER_MAP, DIFFERENT, UNMAPPED, ONLY_IN_STA, ONLY_IN_SOURCE)
_WORST_FIRST = (DIFFERENT, UNMAPPED, EQUAL_AFTER_MAP, EQUAL)

NOT_RECORDED = "not recorded"
NO_STA_ROW = "no STA row valid then"
AFTER_FOUND = "STA row found"
AFTER_MISSING = "no STA row for the change"
AFTER_NOT_RECORDED = "changed, nothing written after"

NO_NAME = "no STA name"
SEVERAL_NAMES = "several STA names"


# --- the name map ---------------------------------------------------------------------


class NameMapError(ValueError):
    """equipment_names.yaml is malformed. The message says where."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that refuses a duplicate key instead of keeping the last one."""


def _unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    seen: set = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise NameMapError(f"duplicate key {key!r} (line {key_node.start_mark.line + 1})")
        seen.add(key)
    return loader.construct_mapping(node, deep)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


@dataclass(frozen=True)
class NameMap:
    receiver: Mapping[str, str]
    antenna: Mapping[str, str]
    radome: Mapping[str, str]
    path: str = ""

    def lookup(self, kind: str, text: str) -> str | None:
        return getattr(self, kind).get(text.strip())


def load_name_map(path: Path | str = DEFAULT_NAME_MAP) -> NameMap:
    path = Path(path)
    try:
        raw = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)  # noqa: S506 -- a SafeLoader subclass
    except yaml.YAMLError as exc:
        raise NameMapError(f"{path}: not valid YAML: {exc}") from None
    if not isinstance(raw, dict):
        raise NameMapError(f"{path}: expected a mapping at the top")
    extra = sorted(set(raw) - {"version", *KINDS})
    if extra:
        raise NameMapError(f"{path}: unknown top-level key(s) {extra}")
    if raw.get("version") != 1:
        raise NameMapError(f"{path}: version must be 1, got {raw.get('version')!r}")
    sections: dict[str, dict[str, str]] = {}
    for kind in KINDS:
        section = raw.get(kind)
        if not isinstance(section, dict):
            raise NameMapError(f"{path}: '{kind}' must be a mapping of name -> IGS name")
        for key, value in section.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise NameMapError(f"{path}: {kind}: {key!r}: {value!r}: names must be text")
            if value != value.strip().upper() or not value:
                raise NameMapError(
                    f"{path}: {kind}: {key!r}: {value!r} is not an IGS name (upper case, no "
                    "surrounding blanks)"
                )
        sections[kind] = {k.strip(): v for k, v in section.items()}
    return NameMap(**sections, path=str(path))


# --- sources ----------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceEquipment:
    station: str
    receiver: str
    antenna: str
    radome: str
    note: str = ""


def read_equipment_csv(path: Path | str) -> dict[str, SourceEquipment]:
    """The network inventory sheet (data/network_inventory/equipment.csv): one row
    per station. Raises ValueError on a missing column."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        need = {"station_code", "model", "antenna_model", "radome_type"}
        missing = sorted(need - set(reader.fieldnames or []))
        if missing:
            raise ValueError(f"{path}: missing column(s) {missing}")
        out: dict[str, SourceEquipment] = {}
        for row in reader:
            code = (row["station_code"] or "").strip().upper()
            if not code:
                continue
            if code in out:
                raise ValueError(f"{path}: station {code} appears twice")
            out[code] = SourceEquipment(
                code,
                (row["model"] or "").strip(),
                (row["antenna_model"] or "").strip(),
                (row["radome_type"] or "").strip(),
            )
    return out


@dataclass
class LogsheetExport:
    path: str
    exported_at: str
    counts: dict
    logsheets: list[dict]
    equipment_history: list[dict]


def read_logsheet_export(path: Path | str) -> LogsheetExport:
    """A file written by scripts/export_field_equipment.py. Raises ValueError if
    it is not one, OSError if it cannot be read."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: not JSON: {exc}") from None
    if not isinstance(doc, dict) or doc.get("format") != EXPORT_FORMAT:
        raise ValueError(f"{path}: not a {EXPORT_FORMAT} file")
    if not isinstance(doc.get("exported_at"), str):
        raise ValueError(f"{path}: has no exported_at timestamp")
    for key in ("logsheets", "equipment_history"):
        if not isinstance(doc.get(key), list):
            raise ValueError(f"{path}: '{key}' must be a list")
    return LogsheetExport(
        str(path), doc["exported_at"], dict(doc.get("counts") or {}),
        doc["logsheets"], doc["equipment_history"],
    )  # fmt: skip


def source_from_history(rows: Iterable[dict]) -> dict[str, SourceEquipment]:
    """Current equipment from equipment_history rows (date_removed null).

    A row may describe a receiver, an antenna or both, so a station's current
    rows are merged. Two current values for one field are both shown, joined
    with " / ", and can match nothing: a person must close one of the rows.
    """
    values: dict[str, dict[str, list[str]]] = {}
    for r in rows:
        if r.get("date_removed"):
            continue
        code = (r.get("station_code") or "").strip().upper()
        if not code:
            continue
        slot = values.setdefault(code, {k: [] for k in KINDS})
        for kind, col in (
            ("receiver", "model"),
            ("antenna", "antenna_model"),
            ("radome", "radome_type"),
        ):
            v = (r.get(col) or "").strip()
            if v and v not in slot[kind]:
                slot[kind].append(v)
    out = {}
    for code, slot in values.items():
        several = [k for k in KINDS if len(slot[k]) > 1]
        out[code] = SourceEquipment(
            code, *(" / ".join(slot[k]) for k in KINDS),
            note=f"several current equipment_history rows for {', '.join(several)}" if several else "",
        )  # fmt: skip
    return out


# --- judging one field --------------------------------------------------------------------


@dataclass(frozen=True)
class FieldResult:
    sta: str
    source: str
    status: str
    source_igs: str | None = None  # what the name map says the source's text means
    note: str = ""


def judge(kind: str, sta: str, source: str, names: NameMap) -> FieldResult:
    sta, source = sta.strip(), source.strip()
    if not source:
        return FieldResult(sta, source, UNMAPPED, note="blank in the source")
    if source == sta:
        return FieldResult(sta, source, EQUAL, source_igs=sta)
    igs = names.lookup(kind, source)
    if igs is None:
        return FieldResult(sta, source, UNMAPPED)
    return FieldResult(sta, source, EQUAL_AFTER_MAP if igs == sta else DIFFERENT, source_igs=igs)


def _worst(statuses: Iterable[str]) -> str:
    present = set(statuses)
    return next((s for s in _WORST_FIRST if s in present), EQUAL)


def _split_antenna(row: StaRow) -> tuple[str, str]:
    """The .STA antenna field is the IGS model in 16 columns, then the radome in 4."""
    return row.antenna[:16].strip(), row.antenna[16:].strip()


def _latest(rows: list[StaRow]) -> StaRow:
    """The row with the latest FROM; a FROM that does not parse sorts first, and
    of two equal FROMs the later line wins. TO does not matter: an open end may
    be blank or 2099-12-31, and either way it is the latest row."""
    return max(rows, key=lambda r: (r.start or dt.datetime.min, r.line))


def _by_code(rows: Iterable[StaRow]) -> dict[str, list[StaRow]]:
    out: dict[str, list[StaRow]] = {}
    for r in rows:
        out.setdefault(r.code, []).append(r)
    return out


# --- 2a: current equipment ---------------------------------------------------------------


@dataclass
class CurrentResult:
    station: str
    category: str
    sta_name: str = ""
    sta_line: int | None = None
    sta_from: str = ""
    sta_to: str = ""
    fields: dict[str, FieldResult] = field(default_factory=dict)
    note: str = ""


def compare_current(
    rows: list[StaRow], source: Mapping[str, SourceEquipment], names: NameMap
) -> list[CurrentResult]:
    by_code = _by_code(rows)
    out: list[CurrentResult] = []
    for code in sorted(set(by_code) | set(source)):
        if code not in source:
            row = _latest(by_code[code])
            out.append(
                CurrentResult(
                    code,
                    ONLY_IN_STA,
                    row.name,
                    row.line,
                    row.from_field.strip(),
                    row.to_field.strip(),
                )
            )
            continue
        if code not in by_code:
            out.append(CurrentResult(code, ONLY_IN_SOURCE, note=source[code].note))
            continue
        row, src = _latest(by_code[code]), source[code]
        ant, radome = _split_antenna(row)
        fields = {
            "receiver": judge("receiver", row.receiver, src.receiver, names),
            "antenna": judge("antenna", ant, src.antenna, names),
            "radome": judge("radome", radome, src.radome, names),
        }
        out.append(
            CurrentResult(
                code,
                _worst(f.status for f in fields.values()),
                row.name,
                row.line,
                row.from_field.strip(),
                row.to_field.strip(),
                fields,
                src.note,
            )  # fmt: skip
        )
    return out


def unmapped_names(results: Iterable[CurrentResult]) -> dict[str, list[str]]:
    """Every source name the map does not know, by kind, for the processing lead."""
    out: dict[str, set[str]] = {k: set() for k in KINDS}
    for r in results:
        for kind, f in r.fields.items():
            if f.status == UNMAPPED and f.source:
                out[kind].add(f.source)
    return {k: sorted(v) for k, v in out.items()}


# --- 2b: per visit -------------------------------------------------------------------------


@dataclass
class VisitResult:
    station: str
    visit_date: str
    visit_time: str  # UTC, ISO, no offset: the .STA's FROM/TO are UTC
    visit_time_source: str  # arrival_time | visit_date
    equipment_changed: bool
    before_status: str
    before_fields: dict[str, FieldResult] = field(default_factory=dict)
    before_row_line: int | None = None
    after_status: str | None = None
    after_fields: dict[str, str] = field(default_factory=dict)
    after_row_line: int | None = None
    after_row_from: str = ""
    note: str = ""


def _visit_time(sheet: dict) -> tuple[dt.datetime, str]:
    arrival = sheet.get("arrival_time")
    if arrival:
        t = dt.datetime.fromisoformat(arrival)
        if t.tzinfo is not None:
            t = t.astimezone(dt.UTC).replace(tzinfo=None)
        return t, "arrival_time"
    return dt.datetime.fromisoformat(sheet["visit_date"]), "visit_date"


def _valid_at(rows: list[StaRow], t: dt.datetime) -> StaRow | None:
    """The row whose [FROM, TO] holds t; of several, the latest FROM. An open end
    (blank, or 2099-12-31) holds every later time, and a blank FROM every earlier
    one, as the header validator reads it. A row whose dates do not parse is left
    out (sta_row_dates_usable), as station_files leaves it out."""
    hits = [
        r
        for r in rows
        if sta_row_dates_usable(r)
        and (r.start is None or r.start <= t)
        and (r.end is None or t <= r.end)
    ]
    return max(hits, key=lambda r: (r.start or dt.datetime.min, r.line)) if hits else None


def compare_visits(rows: list[StaRow], export: LogsheetExport, names: NameMap) -> list[VisitResult]:
    by_code = _by_code(rows)
    out: list[VisitResult] = []
    for sheet in export.logsheets:
        code = (sheet.get("station_code") or "").strip().upper()
        t, t_source = _visit_time(sheet)
        changed = bool(sheet.get("equipment_changed"))
        res = VisitResult(
            code, sheet.get("visit_date") or "", t.isoformat(), t_source, changed, NOT_RECORDED
        )
        station_rows = by_code.get(code, [])
        if not station_rows:
            res.before_status = ONLY_IN_SOURCE
            res.note = "no TYPE 002 row for this code"
            out.append(res)
            continue

        # Before: what the observer found, against the row valid at the visit.
        before = {
            "receiver": (sheet.get("receiver_model_before") or "").strip(),
            "antenna": (sheet.get("antenna_type_before") or "").strip(),
        }
        row = _valid_at(station_rows, t)
        if row is None:
            res.before_status = NO_STA_ROW
        elif any(before.values()):
            ant, _ = _split_antenna(row)
            sta_vals = {"receiver": row.receiver, "antenna": ant}
            res.before_fields = {k: judge(k, sta_vals[k], v, names) for k, v in before.items() if v}
            res.before_status = _worst(f.status for f in res.before_fields.values())
            res.before_row_line = row.line

        # After: a change should have a row from the visit's date on with the new equipment.
        if changed:
            after = {
                "receiver": (sheet.get("receiver_model_after") or "").strip(),
                "antenna": (sheet.get("antenna_type_after") or "").strip(),
            }
            after = {k: v for k, v in after.items() if v}
            if not after:
                res.after_status = AFTER_NOT_RECORDED
            else:
                igs = {
                    k: (v if _is_sta_name(k, v, station_rows) else names.lookup(k, v))
                    for k, v in after.items()
                }
                if any(v is None for v in igs.values()):
                    res.after_status = UNMAPPED
                    res.after_fields = {k: v for k, v in after.items() if igs[k] is None}
                else:
                    res.after_fields = {k: str(v) for k, v in igs.items()}
                    # visit_date is local (PHT, UTC+8) and .STA times are UTC: a
                    # morning swap falls on the previous UTC date. Search from the
                    # start of the UTC date of the arrival, or of the visit date
                    # when there is no arrival, whichever is earlier.
                    day = dt.datetime.fromisoformat(sheet["visit_date"])
                    since = dt.datetime.combine(min(t, day).date(), dt.time.min)
                    match = _first_row_with(station_rows, since, res.after_fields)
                    if match is None:
                        res.after_status = AFTER_MISSING
                    else:
                        res.after_status = AFTER_FOUND
                        res.after_row_line = match.line
                        res.after_row_from = match.from_field.strip()
        out.append(res)
    return out


def _is_sta_name(kind: str, text: str, rows: list[StaRow]) -> bool:
    """The text is, as written, a name these rows use: no map needed."""
    for r in rows:
        if (r.receiver if kind == "receiver" else _split_antenna(r)[0]) == text:
            return True
    return False


def _first_row_with(
    rows: list[StaRow], since: dt.datetime, want: Mapping[str, str]
) -> StaRow | None:
    hits = []
    for r in rows:
        if r.start is None or r.start < since:
            continue
        have = {"receiver": r.receiver, "antenna": _split_antenna(r)[0]}
        if all(have[k] == v for k, v in want.items()):
            hits.append(r)
    return min(hits, key=lambda r: (r.start, r.line)) if hits else None


# --- 2c: station names ---------------------------------------------------------------------


@dataclass(frozen=True)
class NameProblem:
    station: str
    problem: str
    sta_names: list[str]


def check_names(rows: Iterable[StaRow], codes: Iterable[str]) -> list[NameProblem]:
    names = sta_names(rows)
    out = []
    for code in sorted(set(codes)):
        found = sorted(names.get(code, set()))
        if not found:
            out.append(NameProblem(code, NO_NAME, []))
        elif len(found) > 1:
            out.append(NameProblem(code, SEVERAL_NAMES, found))
    return out


# --- the report ---------------------------------------------------------------------------


def build_report(
    sta_path: Path,
    names: NameMap,
    equipment_csv: Path | None = None,
    export: LogsheetExport | None = None,
) -> dict:
    rows = sta_type002_rows(read_text(sta_path))
    current: list[CurrentResult] = []
    current_source = None
    codes: set[str] = set()
    if equipment_csv is not None:
        source = read_equipment_csv(equipment_csv)
        current_source = f"equipment CSV {equipment_csv}"
    elif export is not None and export.equipment_history:
        source = source_from_history(export.equipment_history)
        current_source = f"equipment_history in {export.path}"
    else:
        source = {}
    if current_source:
        current = compare_current(rows, source, names)
        codes |= set(source)
    visits = compare_visits(rows, export, names) if export is not None else []
    codes |= {v.station for v in visits if v.station}
    summary = {c: sum(1 for r in current if r.category == c) for c in CATEGORIES}
    return {
        "advisory": "read-only; never blocks a run",
        "sta": {"path": str(sta_path), "rows": len(rows), "codes": len({r.code for r in rows})},
        "name_map": names.path,
        "sources": {
            "equipment_csv": (
                {
                    "path": str(equipment_csv),
                    "exported_at": None,
                    "note": "export time not recorded in the file",
                }
                if equipment_csv is not None
                else None
            ),
            "logsheet_export": (
                {"path": export.path, "exported_at": export.exported_at, "counts": export.counts}
                if export is not None
                else None
            ),
            "current_equipment_from": current_source,
        },  # fmt: skip
        "summary": summary,
        "current": [_plain(r) for r in current],
        "visits": [_plain(v) for v in visits],
        "names": [asdict(p) for p in check_names(rows, codes)],
        "unmapped": unmapped_names(current),
    }


def _plain(obj: object) -> dict:
    return asdict(obj)  # type: ignore[arg-type]


def _fieldcell(f: Mapping | None) -> str:
    if not f:
        return "-"
    if f["status"] == EQUAL:
        return f["sta"]
    shown = f["source"] or "(blank)"
    if f.get("source_igs") and f["source_igs"] != f["source"]:
        shown += f" [{f['source_igs']}]"
    return f"{f['sta'] or '(blank)'} | {shown}"


def format_report(rep: dict) -> str:
    out = ["bernese-check-equipment: advisory, read-only; it never blocks a run."]
    out.append(
        f"STA:       {rep['sta']['path']} ({rep['sta']['rows']} TYPE 002 rows, {rep['sta']['codes']} codes)"
    )
    out.append(f"name map:  {rep['name_map']}")
    src = rep["sources"]
    if src["equipment_csv"]:
        out.append(
            f"sheet:     {src['equipment_csv']['path']} (export time: not recorded in the file)"
        )
    if src["logsheet_export"]:
        e = src["logsheet_export"]
        counts = ", ".join(f"{v} {k}" for k, v in e["counts"].items())
        out.append(f"export:    {e['path']} (exported_at {e['exported_at']}; {counts})")

    if src["current_equipment_from"]:
        out.append("")
        out.append(f"CURRENT EQUIPMENT: latest STA row against {src['current_equipment_from']}")
        out.append("  " + ", ".join(f"{k} {v}" for k, v in rep["summary"].items()))
        out.append("  cells: STA | source [what the name map makes of it]")
        for r in rep["current"]:
            if r["category"] == EQUAL:
                continue
            f = r["fields"]
            out.append(
                f"  {r['station']:4}  {r['category']:<21}  rcv {_fieldcell(f.get('receiver'))};  "
                f"ant {_fieldcell(f.get('antenna'))};  radome {_fieldcell(f.get('radome'))}"
                + (f"  ({r['note']})" if r["note"] else "")
            )

    if rep["visits"]:
        out.append("")
        out.append(
            "VISITS: STA row valid at the visit against *_before; a change against later rows"
        )
        for v in rep["visits"]:
            line = f"  {v['station']:4}  {v['visit_time']} ({v['visit_time_source']})  before: {v['before_status']}"
            for k, f in v["before_fields"].items():
                if f["status"] != EQUAL:
                    line += f"; {k} {_fieldcell(f)}"
            if v["after_status"]:
                line += f"  after: {v['after_status']}"
                if v["after_row_from"]:
                    line += f" (from {v['after_row_from']}, line {v['after_row_line']})"
            if v["note"]:
                line += f"  ({v['note']})"
            out.append(line)

    if rep["names"]:
        out.append("")
        out.append("STATION NAMES")
        for p in rep["names"]:
            out.append(
                f"  {p['station']:4}  {p['problem']}"
                + (f": {', '.join(p['sta_names'])}" if p["sta_names"] else "")
            )

    un = rep["unmapped"]
    if any(un.values()):
        out.append("")
        out.append(
            "UNMAPPED NAMES: for the processing lead to add to the name map, or correct at the source"
        )
        for kind, values in un.items():
            if values:
                out.append(f"  {kind}: " + ", ".join(repr(v) for v in values))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="bernese-check-equipment",
        description="Compare a .STA file's equipment with field-ops records. Advisory and "
        "read-only: exits 0 whatever it finds, 2 only for unreadable input.",
    )
    ap.add_argument("--sta", type=Path, required=True, help="station information file (.STA)")
    ap.add_argument("--equipment-csv", type=Path, help="network inventory sheet (equipment.csv)")
    ap.add_argument(
        "--logsheet-export", type=Path,
        help="JSON written by scripts/export_field_equipment.py (logsheets, equipment_history)",
    )  # fmt: skip
    ap.add_argument("--name-map", type=Path, default=DEFAULT_NAME_MAP)
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    args = ap.parse_args(argv)
    if args.equipment_csv is None and args.logsheet_export is None:
        ap.error("give --equipment-csv, --logsheet-export, or both")
    try:
        names = load_name_map(args.name_map)
        export = read_logsheet_export(args.logsheet_export) if args.logsheet_export else None
        rep = build_report(args.sta, names, args.equipment_csv, export)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"cannot read: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(rep, indent=1) if args.json else format_report(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
