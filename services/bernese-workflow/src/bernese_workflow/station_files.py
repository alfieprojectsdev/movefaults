"""Check a campaign's station files the way Bernese reads them, before a run.

WHY THIS EXISTS
Bernese drops a station for the whole day, without failing the run, when its
STA TYPE 002 rows overlap in time. On gps3 that happened to one station every
day: one row was left open to 2099, a second duplicated another, and a third
started a new receiver while the first was still open. A scan of that file
found overlaps for three more stations. Ocean loading has two traps of the
same kind (docs/SETTLED.md §2): a BLQ block after `$$ END TABLE` is never
read, and an ATL block is matched on the full station name, so `PTAG` and
`PTAG 22006M005` are different stations. Every one of these reads as correct
on inspection and surfaces, if at all, as NOT FOUND or a missing station.

WHAT IT REPORTS
  STA  per full station name: TYPE 002 windows that overlap; exact duplicate
       rows; a row open to 2099 (or with TO blank) that a later row follows;
       a row whose FROM is after its TO; a date column that does not parse.
       An end equal to the next start is the IGS convention, not an overlap.
  BLQ  every station block after `$$ END TABLE`.
  ATL  every block header whose code is in the STA under a different full name,
       unless the header is another station's name in the CRD.
  RINEX  stations with RINEX on a day to be run but absent from the STA, the
       CRD or the BLQ (the BLQ check also says why: after END TABLE,
       indented one column, or absent).

WHICH FINDINGS BLOCK
run_plan puts a blocking finding in RunPlan.problems, where each entry refuses
the run, and the rest in RunPlan.warnings. Blocking: every overlap form
(duplicate and open-ended rows are overlaps with a known cause), every block
after END TABLE, and a station with RINEX to run that the STA, CRD or BLQ does
not have (the header validator already treats a station missing from the STA
as an error, and a missing BLQ entry stops GPSEDT). An ATL name mismatch
blocks only for a station with RINEX in the days to run, since GTATML stops
the run on it; for other stations it is a warning. A reversed window and an
unreadable date are warnings: what Bernese does with them has not been
observed, so they are reported rather than allowed to refuse a run.

SHARED READERS
The STA rows come from rinex_header_validator.sta_type002_rows, the RINEX
station-days from the datapool scan run_plan already makes. The CRD, BLQ and
ATL readers below were scripts/check_ref_coverage.py's and moved here so that
script and this module read the files one way; it imports them from here.

Nothing here writes a file. Files are read in text mode, which accepts CRLF
and LF alike; since nothing is written back, the line endings on disk are
never touched.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .rinex_header_validator import StaRow, sta_type002_rows

if TYPE_CHECKING:
    from pogf_geodetic_suite.qc.completeness import Coverage

# pogf_geodetic_suite is imported where it is used, not here: it pulls in
# click, and scripts/check_ref_coverage.py imports this module under a plain
# system python3 that has neither.

# A TO date in or after this year is how Bernese files write "still valid".
OPEN_YEAR = 2099

_CRD_LINE = re.compile(r"^\s*\d+\s{2}(\S{4}.{12})\s*-?\d+\.\d+\s+-?\d+\.\d+\s+-?\d+\.\d+")
_END_TABLE = "$$ END TABLE"


# ---------------------------------------------------------------------------
# Readers (moved from scripts/check_ref_coverage.py, which imports them)
# ---------------------------------------------------------------------------


def _lines(text: str) -> list[str]:
    return [line.rstrip("\r") for line in text.split("\n")]


def crd_names(text: str) -> dict[str, list[str]]:
    """Code -> every full station name with that code (columns 6-21, blanks dropped).

    A code is not unique: LUZON.CRD carries both `BILI 12363M001` (the IGS
    fiducial) and `BILI BILI` (the PHIVOLCS site). Keeping only one would make
    CRD line order decide which station gets checked.
    """
    names: dict[str, list[str]] = {}
    for line in _lines(text):
        m = _CRD_LINE.match(line)
        if m:
            full = m[1].rstrip()
            names.setdefault(full[:4], []).append(full)
    return names


def name_listed(text: str, full_name: str) -> bool:
    """True if some line starts with the full name and its name field ends there.

    The name field is 16 wide and followed by at least two blanks in both STA
    and ABB, while a name holds at most single blanks. So `PTAG 22006M005`
    does not list the bare name `PTAG`, which is a different key to Bernese.
    """
    for line in _lines(text):
        rest = line[len(full_name) :]
        if line.startswith(full_name) and (not rest.strip() or rest.startswith("  ")):
            return True
    return False


def _blq_header_code(line: str) -> str | None:
    """The code of a BLQ block header in the column Bernese reads (3), else None.

    Two blanks, four characters, then a blank or the end of the line. Data rows
    also start with two blanks but carry numbers (`  .01857`), so the four
    characters are not alphanumeric.
    """
    code = line[2:6]
    if line[:2] == "  " and line[6:7] in ("", " ") and len(code) == 4 and code.isalnum():
        return code
    return None


def blq_status(text: str, code: str) -> str:
    """'ok', 'after END TABLE', 'indented 1 column' or 'absent'."""
    seen_end = False
    found_after = misindented = False
    for line in _lines(text):
        if line.startswith(_END_TABLE):
            seen_end = True
            continue
        if line.startswith("$$"):
            continue
        if _blq_header_code(line) == code:
            if not seen_end:
                return "ok"
            found_after = True
        elif (
            line[1:5] == code
            and line[:1] == " "
            and line[1:2] != " "
            and line[5:6] in ("", " ")
            and not seen_end
        ):
            misindented = True
    if found_after:
        return "after END TABLE"
    if misindented:
        return "indented 1 column"
    return "absent"


def _blq_headers(text: str) -> list[tuple[str, int, bool]]:
    """(code, line number, after the first `$$ END TABLE`) for every block header."""
    out: list[tuple[str, int, bool]] = []
    seen_end = False
    for number, line in enumerate(_lines(text), start=1):
        if line.startswith(_END_TABLE):
            seen_end = True
        elif code := _blq_header_code(line):
            out.append((code, number, seen_end))
    return out


def atl_headers(text: str) -> list[tuple[str, int]]:
    """(header, line number) of every ATL block header: unindented, not `$$`."""
    return [
        (line.rstrip(), number)
        for number, line in enumerate(_lines(text), start=1)
        if line and not line.startswith(("$$", " "))
    ]


def atl_status(text: str, full_name: str) -> str:
    """'ok', "header 'X' != 'NAME'", or 'absent'. Headers are unindented."""
    code = full_name[:4]
    near = None
    for header, _ in atl_headers(text):
        if header == full_name:
            return "ok"
        if header[:4] == code and near is None:
            near = header
    if near is not None:
        return f"header '{near}' != '{full_name}'"
    return "absent"


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """One defect in one file. ``str()`` is the line a plan prints."""

    file: str  # file name as reported, e.g. PHNAT.STA
    kind: str  # see KINDS
    station: str  # full name for STA/ATL findings, the 4-char code otherwise
    detail: str
    blocking: bool

    def __str__(self) -> str:
        return f"{self.file}: {self.station}: {self.detail}"


KINDS = (
    "sta_overlap",
    "sta_duplicate",
    "sta_open_then_later",
    "sta_reversed",
    "sta_bad_date",
    "sta_empty",
    "blq_after_end_table",
    "atl_name",
    "missing_sta",
    "missing_crd",
    "missing_blq",
)


def _fmt(row: StaRow, which: str) -> str:
    return (row.from_field if which == "from" else row.to_field).strip() or "blank"


def _is_open(row: StaRow) -> bool:
    return row.end is None or row.end.year >= OPEN_YEAR


def _overlap(a: StaRow, b: StaRow) -> bool:
    """Both windows cover a common moment. A shared boundary does not count:
    the IGS convention ends one row exactly where the next begins."""
    a_lo, b_lo = a.start, b.start
    a_hi, b_hi = a.end, b.end
    return (a_lo is None or b_hi is None or a_lo < b_hi) and (
        b_lo is None or a_hi is None or b_lo < a_hi
    )


def _start_key(row: StaRow) -> tuple[int, object, int]:
    # None (open start) sorts first; the line number keeps ties in file order.
    return (0, 0, row.line) if row.start is None else (1, row.start, row.line)


def check_sta(text: str, label: str, rows: list[StaRow] | None = None) -> list[Finding]:
    """TYPE 002 defects, per full station name (the key Bernese uses).

    Each offending pair is reported once, under the most specific cause:
    an exact duplicate, then an open-ended row that a later row follows, then a
    plain overlap. All three are overlaps to Bernese, and all three block.
    ``rows``: ``sta_type002_rows(text)`` when the caller already has it.
    """
    if rows is None:
        rows = sta_type002_rows(text)
    if not rows:
        return [Finding(label, "sta_empty", "-", "no TYPE 002 rows were read", True)]
    out: list[Finding] = []
    by_name: dict[str, list[StaRow]] = {}
    for r in rows:
        by_name.setdefault(r.name, []).append(r)

    for name, group in by_name.items():
        usable: list[StaRow] = []
        for r in group:
            bad = [
                f"{which} '{raw.strip()}'"
                for which, raw, parsed in (
                    ("FROM", r.from_field, r.start),
                    ("TO", r.to_field, r.end),
                )
                if raw.strip() and parsed is None
            ]
            if bad:
                out.append(
                    Finding(label, "sta_bad_date", name,
                            f"line {r.line}: {' and '.join(bad)} does not parse; "
                            "the row was left out of the overlap check", False)
                )  # fmt: skip
                continue
            if r.start is not None and r.end is not None and r.start > r.end:
                out.append(
                    Finding(label, "sta_reversed", name,
                            f"line {r.line}: FROM {_fmt(r, 'from')} is after "
                            f"its own TO {_fmt(r, 'to')}", False)
                )  # fmt: skip
                continue
            usable.append(r)

        first_seen: dict[str, StaRow] = {}
        for r in usable:
            if r.text in first_seen:
                out.append(
                    Finding(label, "sta_duplicate", name,
                            f"line {r.line} repeats line {first_seen[r.text].line} exactly", True)
                )  # fmt: skip
            else:
                first_seen[r.text] = r

        ordered = sorted(usable, key=_start_key)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1 :]:
                if a.text == b.text or not _overlap(a, b):
                    continue
                later = b.start is not None and (a.start is None or b.start > a.start)
                if _is_open(a) and later:
                    out.append(
                        Finding(label, "sta_open_then_later", name,
                                f"line {a.line} is open (TO {_fmt(a, 'to')}) but line {b.line} "
                                f"starts {_fmt(b, 'from')}; close line {a.line} there", True)
                    )  # fmt: skip
                else:
                    out.append(
                        Finding(label, "sta_overlap", name,
                                f"line {a.line} ({_fmt(a, 'from')} to {_fmt(a, 'to')}) overlaps "
                                f"line {b.line} ({_fmt(b, 'from')} to {_fmt(b, 'to')})", True)
                    )  # fmt: skip
    return out


def check_blq(text: str, label: str) -> list[Finding]:
    """Every block after `$$ END TABLE`: Bernese never reads it."""
    headers = _blq_headers(text)
    above = {code for code, _, after in headers if not after}
    out = []
    for code, number in ((c, n) for c, n, after in headers if after):
        note = (
            "; the block above the marker is the one Bernese reads"
            if code in above
            else "; Bernese will report its coefficients NOT FOUND"
        )
        out.append(
            Finding(label, "blq_after_end_table", code,
                    f"line {number}: block is after $$ END TABLE{note}", True)
        )  # fmt: skip
    return out


def sta_names(rows: Iterable[StaRow]) -> dict[str, set[str]]:
    """Code -> the full names the STA gives it (usually one; BILI has two)."""
    out: dict[str, set[str]] = {}
    for r in rows:
        out.setdefault(r.code, set()).add(r.name)
    return out


def check_atl(
    text: str,
    label: str,
    names: Mapping[str, set[str]],
    active: Iterable[str] = (),
    other_stations: Iterable[str] = (),
) -> list[Finding]:
    """ATL headers whose code is a STA station but whose name is not its STA name.

    ATL is matched on the full name, so a header `PTAG` is NOT FOUND for
    `PTAG 22006M005`. Headers for codes the STA does not have are not this
    campaign's stations (LUZON.ATL carries hundreds of global sites) and are
    left alone. ``other_stations``: full names known to be real stations (the
    CRD's), so a header naming one is another station that shares the code,
    not a misnamed one; LUZON.ATL's `BILI 12363M001` is the IGS fiducial beside
    the STA's `BILI BILI`. ``active``: codes with RINEX to run; a mismatch
    blocks only for those.
    """
    active, other = set(active), set(other_stations)
    out = []
    for header, number in atl_headers(text):
        code = header[:4]
        expected = names.get(code)
        if not expected or header in expected or header in other:
            continue
        want = " or ".join(f"'{n}'" for n in sorted(expected))
        out.append(
            Finding(label, "atl_name", code,
                    f"line {number}: header '{header}' is not the STA name {want}",
                    code in active)
        )  # fmt: skip
    return out


def check_rinex_stations(
    coverage: Coverage,
    days: Iterable[int],
    *,
    names: Mapping[str, set[str]],
    sta_label: str,
    crd_text: str | None = None,
    crd_label: str = "CRD",
    blq_text: str | None = None,
    blq_label: str = "BLQ",
    sta_read: bool = True,
) -> list[Finding]:
    """Stations with RINEX on one of ``days`` but absent from the STA, CRD or BLQ.

    One finding per station and file, with the days compressed into ranges.
    The CRD must carry one of the station's STA names, since that is the name
    Bernese looks up; a code the STA lacks is checked by code alone.
    ``sta_read`` False: the STA yielded no rows, which check_sta already
    reports once as sta_empty; a missing_sta line for every station would
    bury that one finding, so STA presence is not checked.
    """
    from pogf_geodetic_suite.qc.completeness import compress_ranges

    crd = crd_names(crd_text) if crd_text is not None else None

    def why_missing(code: str) -> list[tuple[str, str, str]]:
        """(kind, file label, reason) for each file that lacks ``code``."""
        out = []
        if sta_read and code not in names:
            out.append(("missing_sta", sta_label, "no TYPE 002 row"))
        if crd is not None:
            in_crd, wanted = crd.get(code, []), names.get(code, set())
            if not in_crd:
                out.append(("missing_crd", crd_label, "absent"))
            elif wanted and not wanted & set(in_crd):
                out.append(
                    ("missing_crd", crd_label,
                     f"CRD names {', '.join(map(repr, in_crd))}, "
                     f"STA names {', '.join(map(repr, sorted(wanted)))}")
                )  # fmt: skip
        if blq_text is not None and (status := blq_status(blq_text, code)) != "ok":
            out.append(("missing_blq", blq_label, status))
        return out

    # A station's files do not change from day to day, so ask once per station.
    days_by_code: dict[str, list[int]] = {}
    for doy in sorted(set(days)):
        for code in coverage.by_day.get(doy, set()):
            days_by_code.setdefault(code, []).append(doy)
    return [
        Finding(label, kind, code, f"RINEX on DOY {compress_ranges(doys)} but {why}", True)
        for code, doys in sorted(days_by_code.items())
        for kind, label, why in why_missing(code)
    ]


def check_station_files(
    *,
    sta: tuple[str, str],
    crd: tuple[str, str] | None = None,
    blq: tuple[str, str] | None = None,
    atl: tuple[str, str] | None = None,
    coverage: Coverage | None = None,
    days: Iterable[int] = (),
) -> list[Finding]:
    """Every finding for one campaign's files. Each file is ``(label, text)``.

    ``crd``/``blq``/``atl`` None: that file is not checked (a PCF with V_BLQINF
    or V_ATLINF blank does not use it). ``coverage`` None: the RINEX checks are
    skipped; the caller is expected to say so, as run_plan does.
    """
    sta_label, sta_text = sta
    days = list(days)
    rows = sta_type002_rows(sta_text)
    names = sta_names(rows)
    active = {c for d in days for c in (coverage.by_day.get(d, set()) if coverage else set())}

    out = check_sta(sta_text, sta_label, rows)
    if blq is not None:
        out += check_blq(blq[1], blq[0])
    if atl is not None:
        crd_full = [n for ns in crd_names(crd[1]).values() for n in ns] if crd else []
        out += check_atl(atl[1], atl[0], names, active, other_stations=crd_full)
    if coverage is not None:
        out += check_rinex_stations(
            coverage,
            days,
            names=names,
            sta_label=sta_label,
            crd_text=crd[1] if crd else None,
            crd_label=crd[0] if crd else "CRD",
            blq_text=blq[1] if blq else None,
            blq_label=blq[0] if blq else "BLQ",
            sta_read=bool(rows),
        )
    return out


def read_text(path: Path) -> str:
    """A reference file's text. latin-1 accepts any byte, so a stray accented
    character in a description column cannot stop the check; text mode accepts
    CRLF and LF. Read only: nothing in this module writes."""
    return path.read_text(encoding="latin-1")


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    from pogf_geodetic_suite.qc.completeness import scan

    ap = argparse.ArgumentParser(
        description="Check a campaign's STA, BLQ, ATL and CRD the way Bernese reads them. "
        "Reads only; writes nothing. Inside a planned run the same findings appear "
        "in `bernese-run-year --plan` as PROBLEM and WARNING lines."
    )
    ap.add_argument("--sta", type=Path, required=True, help="station information file (.STA)")
    ap.add_argument("--crd", type=Path, help="coordinate file (.CRD)")
    ap.add_argument("--blq", type=Path, help="ocean loading file (.BLQ)")
    ap.add_argument("--atl", type=Path, help="atmospheric loading file (.ATL)")
    ap.add_argument("--rinex-dir", type=Path, help="datapool directory (V_RNXDIR) to scan")
    ap.add_argument("--year", type=int, help="with --rinex-dir: the year to scan")
    ap.add_argument("--from", dest="doy_from", type=int, default=1)
    ap.add_argument("--to", dest="doy_to", type=int, default=366)
    args = ap.parse_args(argv)
    if args.rinex_dir and args.year is None:
        ap.error("--rinex-dir needs --year")
    if args.rinex_dir and not args.rinex_dir.is_dir():
        # scan() of a missing directory finds nothing, and nothing reads as clean
        ap.error(f"--rinex-dir {args.rinex_dir} is not a directory")

    def load(p: Path | None) -> tuple[str, str] | None:
        return None if p is None else (p.name, read_text(p))

    try:
        sta = (args.sta.name, read_text(args.sta))
        files = {k: load(getattr(args, k)) for k in ("crd", "blq", "atl")}
    except OSError as e:
        print(f"cannot read: {e}", file=sys.stderr)
        return 2
    coverage = scan(args.rinex_dir, args.year) if args.rinex_dir else None
    findings = check_station_files(
        sta=sta, **files, coverage=coverage, days=range(args.doy_from, args.doy_to + 1)
    )
    checked = [args.sta.name] + [p.name for p in (args.crd, args.blq, args.atl) if p]
    if coverage is not None:
        checked.append(f"RINEX in {args.rinex_dir} ({len(coverage.stations)} stations)")
    print(f"checked: {', '.join(checked)}")
    blocking = [f for f in findings if f.blocking]
    for f in findings:
        print(f"  {'PROBLEM' if f.blocking else 'WARNING'}: {f}")
    print(f"{len(blocking)} problem(s), {len(findings) - len(blocking)} warning(s)")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
