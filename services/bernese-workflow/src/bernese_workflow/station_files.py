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
  ATL  every STA station with no block under its full STA name (atl_status:
       absent, or only a header such as `PTAG` for `PTAG 22006M005`); and
       every header whose code is in the STA under a different full name,
       unless the header is another station's name in the CRD.
  ABB  every STA station with no abbreviation line under its full STA name,
       from ${V_CRDINF}.ABB (see run_plan.check_station_files_for_pcf).
  RINEX  stations with RINEX on a day to be run but absent from the STA, the
       CRD or the BLQ (the BLQ check also says why: after END TABLE,
       indented one column, or absent).

WHICH FINDINGS BLOCK
run_plan puts a blocking finding in RunPlan.problems, where each entry refuses
the run, and the rest in RunPlan.warnings. Blocking: an overlap form
(duplicate and open-ended rows are overlaps with a known cause) for a station
with RINEX on a day to run, when the overlap covers that day (S01R, LUZON
2026: Bernese dropped it every day). An overlap for a station with no data in
the run, or one that ended before the run's first day (BTUN, SNFO and SPAB in
LUZON.STA; BTUN, SPAB and URDT in PHNAT.STA), is a warning: it cannot affect
these days, and blocking on it refused runs that solve. Without a datapool
scan (the CLI with no --rinex-dir) every overlap blocks. Also blocking: every block
after END TABLE, and a station with RINEX to run that the STA, CRD or BLQ does
not have (the header validator already treats a station missing from the STA
as an error, and a missing BLQ entry stops GPSEDT). A station with no ATL
block under its full name blocks when it has RINEX in the days to run, since
GTATML stops the run with NOT FOUND (PHDEN DOY 200, docs/SETTLED.md section
2); stations without data are one warning, and without a datapool scan every
one blocks. A stray ATL header beside a correct block is a warning. A reversed
window and an unreadable date are warnings: what Bernese does with them has
not been observed, so they are reported rather than allowed to refuse a run.

ABB IS WARNING ONLY, AND STAYS SO UNTIL A FAILURE IS RECORDED
What Bernese does with a station missing from the abbreviation file has not
been observed in any run here. A missing ABB line is therefore reported, never
allowed to refuse a run. It becomes blocking only after a real failure caused
by it is recorded in config/bernese/bpe_errors.yaml, with the run it came
from; until then a block would rest on a guess.

SHARED READERS
The STA rows come from rinex_header_validator.sta_type002_rows, the RINEX
station-days from the datapool scan run_plan already makes. The CRD, BLQ and
ATL readers below were scripts/check_ref_coverage.py's and moved here so that
script and this module read the files one way; it imports them from here, and
only public names.

Nothing here writes a file. Files are read in text mode, which accepts CRLF
and LF alike; since nothing is written back, the line endings on disk are
never touched.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .rinex_header_validator import StaRow, sta_type002_rows, windows_overlap

if TYPE_CHECKING:
    from pogf_geodetic_suite.qc.completeness import Coverage

# pogf_geodetic_suite is imported where it is used, not here: it pulls in
# click, and scripts/check_ref_coverage.py imports this module under a plain
# system python3 that has neither.

# A TO date in or after this year is how Bernese files write "still valid".
OPEN_YEAR = 2099

_CRD_LINE = re.compile(r"^\s*\d+\s{2}(\S{4}.{12})\s*-?\d+\.\d+\s+-?\d+\.\d+\s+-?\d+\.\d+")
_END_TABLE = "$$ END TABLE"
# What may follow a BLQ header's 4-char code: end of line, a blank, or `_`
_BLQ_NAME_END = ("", " ", "_")


# ---------------------------------------------------------------------------
# Readers (moved from scripts/check_ref_coverage.py, which imports them;
# all public, so the script depends on no private name)
# ---------------------------------------------------------------------------


def split_lines(text: str) -> list[str]:
    """Lines split on ``\\n`` alone, a trailing ``\\r`` dropped: CRLF and LF both
    work, and a stray U+0085 in a description column does not split a line."""
    return [line.rstrip("\r") for line in text.split("\n")]


def crd_names(text: str) -> dict[str, list[str]]:
    """Code -> every full station name with that code (columns 6-21, blanks dropped).

    A code is not unique: LUZON.CRD carries both `BILI 12363M001` (the IGS
    fiducial) and `BILI BILI` (the PHIVOLCS site). Keeping only one would make
    CRD line order decide which station gets checked.
    """
    names: dict[str, list[str]] = {}
    for line in split_lines(text):
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
    for line in split_lines(text):
        rest = line[len(full_name) :]
        if line.startswith(full_name) and (not rest.strip() or rest.startswith("  ")):
            return True
    return False


def _blq_header_code(line: str) -> str | None:
    """The code of a BLQ block header in the column Bernese reads (3), else None.

    Two blanks, four characters, then a blank, an underscore or the end of the
    line. Data rows also start with two blanks but carry numbers (`  .01857`),
    so the four characters are not alphanumeric. The underscore is the OLMPP
    form `  LORE_LORE`: PHNAT.BLQ carries LORE and MONT that way, and PHREF's
    GPSEST read PHNAT.BLQ for both without a NOT FOUND (PHR251700, DOY 170).
    """
    code = line[2:6]
    if line[:2] == "  " and line[6:7] in _BLQ_NAME_END and len(code) == 4 and code.isalnum():
        return code
    return None


def blq_status(text: str, code: str) -> str:
    """'ok', 'after END TABLE', 'indented 1 column' or 'absent'."""
    seen_end = False
    found_after = misindented = False
    for line in split_lines(text):
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
            and line[5:6] in _BLQ_NAME_END
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
    for number, line in enumerate(split_lines(text), start=1):
        if line.startswith(_END_TABLE):
            seen_end = True
        elif code := _blq_header_code(line):
            out.append((code, number, seen_end))
    return out


def atl_headers(text: str) -> list[tuple[str, int]]:
    """(header, line number) of every ATL block header: unindented, not `$$`."""
    return [
        (line.rstrip(), number)
        for number, line in enumerate(split_lines(text), start=1)
        if line and not line.startswith(("$$", " "))
    ]


def atl_status(text: str, full_name: str) -> str:
    """'ok', "header 'X' != 'NAME'", or 'absent'. Headers are unindented."""
    return _atl_status_in([h for h, _ in atl_headers(text)], full_name)


def _atl_status_in(headers: list[str], full_name: str) -> str:
    """atl_status over headers already read, so many names cost one pass."""
    code = full_name[:4]
    near = None
    for header in headers:
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
    # For STA overlap forms: the moment range both rows cover (None = open).
    window: tuple[dt.datetime | None, dt.datetime | None] | None = None

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
    "missing_atl",
    "missing_abb",
)


def _fmt(row: StaRow, which: str) -> str:
    return (row.from_field if which == "from" else row.to_field).strip() or "blank"


def _is_open(row: StaRow) -> bool:
    return row.end is None or row.end.year >= OPEN_YEAR


def _overlap(a: StaRow, b: StaRow) -> bool:
    """Both windows cover a common moment (``windows_overlap``, the rule the
    header check uses too). A shared boundary between two ranges does not
    count; a single-instant row (FROM == TO) at either end of another does."""
    return windows_overlap(a.start, a.end, b.start, b.end)


def _common(a: StaRow, b: StaRow) -> tuple[dt.datetime | None, dt.datetime | None]:
    """The window both rows cover; None at either end means open."""
    starts = [x for x in (a.start, b.start) if x is not None]
    ends = [x for x in (a.end, b.end) if x is not None]
    return (max(starts) if starts else None, min(ends) if ends else None)


_OVERLAP_KINDS = frozenset({"sta_overlap", "sta_duplicate", "sta_open_then_later"})


def _touches(
    window: tuple[dt.datetime | None, dt.datetime | None], lo: dt.datetime, hi: dt.datetime
) -> bool:
    w_lo, w_hi = window
    if w_lo is not None and w_lo == w_hi:
        # A single-instant overlap (windows_overlap): the instant is inside
        # the run when it falls in [lo, hi), including lo itself, the first
        # day's midnight. The strict test below would read that as ending
        # exactly where the run begins.
        return lo <= w_lo < hi
    return (w_lo is None or w_lo < hi) and (w_hi is None or w_hi > lo)


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
                            f"line {r.line} repeats line {first_seen[r.text].line} exactly", True,
                            (r.start, r.end))
                )  # fmt: skip
            else:
                first_seen[r.text] = r

        ordered = sorted(usable, key=_start_key)
        for i, a in enumerate(ordered):
            closed_at_first_later = False
            for b in ordered[i + 1 :]:
                if a.text == b.text or not _overlap(a, b):
                    continue
                later = b.start is not None and (a.start is None or b.start > a.start)
                # Not for a later single-instant row: closing ``a`` at its FROM
                # would still leave ``a`` ending at that instant, which
                # ``windows_overlap`` counts as an overlap.
                if _is_open(a) and later and b.start != b.end:
                    # Closing ``a`` at the first later start also ends its
                    # overlap with every row that starts after that one; a
                    # finding per later row would advise closing it at each.
                    if closed_at_first_later:
                        continue
                    closed_at_first_later = True
                    out.append(
                        Finding(label, "sta_open_then_later", name,
                                f"line {a.line} is open (TO {_fmt(a, 'to')}) but line {b.line} "
                                f"starts {_fmt(b, 'from')}; close line {a.line} there", True,
                                _common(a, b))
                    )  # fmt: skip
                else:
                    out.append(
                        Finding(label, "sta_overlap", name,
                                f"line {a.line} ({_fmt(a, 'from')} to {_fmt(a, 'to')}) overlaps "
                                f"line {b.line} ({_fmt(b, 'from')} to {_fmt(b, 'to')})", True,
                                _common(a, b))
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
    other_stations: Iterable[str] = (),
) -> list[Finding]:
    """ATL headers whose code is a STA station but whose name is not its STA name.

    ATL is matched on the full name, so a header `PTAG` is NOT FOUND for
    `PTAG 22006M005`. Headers for codes the STA does not have are not this
    campaign's stations (LUZON.ATL carries hundreds of global sites) and are
    left alone. ``other_stations``: full names known to be real stations (the
    CRD's), so a header naming one is another station that shares the code,
    not a misnamed one; LUZON.ATL's `BILI 12363M001` is the IGS fiducial beside
    the STA's `BILI BILI`.

    Always a warning. Whether the run can read the station is check_atl_presence's
    question, and it blocks: a station whose only block is misnamed is reported
    there with this same reason, and check_station_files drops the duplicate
    here. What is left is a stray header beside a correct block, which Bernese
    never reads.
    """
    other = set(other_stations)
    out = []
    for header, number in atl_headers(text):
        code = header[:4]
        expected = names.get(code)
        if not expected or header in expected or header in other:
            continue
        want = " or ".join(f"'{n}'" for n in sorted(expected))
        out.append(
            Finding(label, "atl_name", code,
                    f"line {number}: header '{header}' is not the STA name {want}", False)
        )  # fmt: skip
    return out


def atl_missing(text: str, names: Mapping[str, set[str]]) -> dict[str, str]:
    """Code -> atl_status's reason, for STA codes with no block under any STA name."""
    headers = [h for h, _ in atl_headers(text)]
    out = {}
    for code in sorted(names):
        statuses = [_atl_status_in(headers, n) for n in sorted(names[code])]
        if "ok" not in statuses:
            out[code] = statuses[0]
    return out


def check_atl_presence(
    text: str,
    label: str,
    names: Mapping[str, set[str]],
    active_days: Mapping[str, list[int]] | None,
    missing: Mapping[str, str] | None = None,
) -> list[Finding]:
    """STA stations with no ATL block under their full STA name.

    Bernese looks the station up by its full name and stops the run when it is
    not there: `*** SR GTATML ... STATION NAME : PTAG 22006M005`, NOT FOUND,
    with a block headed `PTAG` in the file (docs/SETTLED.md section 2). A code
    the STA gives two names (BILI) passes when either has a block.

    ``active_days``: code -> the days to run that have its RINEX. A station
    with data blocks. Stations without data in the run cannot stop it and are
    gathered into one warning, since a national STA can hold hundreds. None
    means no datapool scan: every station blocks, as overlaps do. ``missing``:
    atl_missing's result, when the caller already has it.
    """
    from pogf_geodetic_suite.qc.completeness import compress_ranges

    if missing is None:
        missing = atl_missing(text, names)
    out: list[Finding] = []
    quiet: list[str] = []
    for code, why in missing.items():
        if active_days is None:
            out.append(
                Finding(label, "missing_atl", code, f"no block under the STA name: {why}", True)
            )
        elif code in active_days:
            days = compress_ranges(active_days[code])
            out.append(Finding(label, "missing_atl", code, f"RINEX on DOY {days} but {why}", True))
        else:
            quiet.append(code if why == "absent" else f"{code} ({why})")
    if quiet:
        out.append(
            Finding(label, "missing_atl", "-",
                    f"{len(quiet)} STA station(s) with no RINEX in this run have no block "
                    f"under their STA name (warning only): {', '.join(quiet)}", False)
        )  # fmt: skip
    return out


def check_abb_presence(
    text: str,
    label: str,
    names: Mapping[str, set[str]],
    active_days: Mapping[str, list[int]] | None,
) -> list[Finding]:
    """STA stations with no abbreviation line under their full STA name. WARNING ONLY.

    The test is check_ref_coverage's: a line that starts with the full name,
    whose 16-column name field ends there (name_listed). Reported for stations
    with RINEX in the run, or for every station without a datapool scan.
    """
    from pogf_geodetic_suite.qc.completeness import compress_ranges

    out: list[Finding] = []
    for code in sorted(names):
        if any(name_listed(text, n) for n in names[code]):
            continue
        want = " or ".join(f"'{n}'" for n in sorted(names[code]))
        if active_days is None:
            why = f"no line for the STA name {want}"
        elif code in active_days:
            why = f"RINEX on DOY {compress_ranges(active_days[code])} but no line for {want}"
        else:
            continue
        out.append(Finding(label, "missing_abb", code, f"{why} (warning only)", False))
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
    abb: tuple[str, str] | None = None,
    coverage: Coverage | None = None,
    days: Iterable[int] = (),
    year: int | None = None,
) -> list[Finding]:
    """Every finding for one campaign's files. Each file is ``(label, text)``.

    ``crd``/``blq``/``atl``/``abb`` None: that file is not checked (a PCF with
    V_BLQINF or V_ATLINF blank does not use it). ``coverage`` None: the RINEX
    checks are skipped; the caller is expected to say so, as run_plan does.
    """
    sta_label, sta_text = sta
    days = list(days)
    rows = sta_type002_rows(sta_text)
    names = sta_names(rows)
    active = {c for d in days for c in (coverage.by_day.get(d, set()) if coverage else set())}

    out = check_sta(sta_text, sta_label, rows)
    if coverage is not None and year is not None:
        # No days to run: nothing an overlap could affect, so active is empty
        # and every overlap scopes down to a warning.
        first, last = (min(days), max(days)) if days else (1, 1)
        lo = dt.datetime(year, 1, 1) + dt.timedelta(days=first - 1)
        hi = dt.datetime(year, 1, 1) + dt.timedelta(days=last)
        out = [_scope_overlap(f, active, lo, hi) for f in out]
    if blq is not None:
        out += check_blq(blq[1], blq[0])
    # code -> the days to run with its RINEX, for STA stations; None: no scan
    active_days: dict[str, list[int]] | None = None
    if coverage is not None:
        active_days = {}
        for d in sorted(set(days)):
            for c in coverage.by_day.get(d, set()):
                if c in names:
                    active_days.setdefault(c, []).append(d)
    if atl is not None:
        missing = atl_missing(atl[1], names)
        crd_full = [n for ns in crd_names(crd[1]).values() for n in ns] if crd else []
        out += [
            f
            for f in check_atl(atl[1], atl[0], names, other_stations=crd_full)
            if f.station not in missing  # reported below, with the same reason
        ]
        out += check_atl_presence(atl[1], atl[0], names, active_days, missing)
    if abb is not None:
        out += check_abb_presence(abb[1], abb[0], names, active_days)
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


def _scope_overlap(f: Finding, active: set[str], lo: dt.datetime, hi: dt.datetime) -> Finding:
    """An STA overlap blocks only for a station with RINEX to run, over the run's days."""
    if f.kind not in _OVERLAP_KINDS or f.window is None:
        return f
    if f.station[:4] in active and _touches(f.window, lo, hi):
        return f
    why = (
        "no RINEX for it on the days to run"
        if f.station[:4] not in active
        else "it does not cover the days to run"
    )
    return Finding(f.file, f.kind, f.station, f"{f.detail} (warning only: {why})", False, f.window)


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
        description="Check a campaign's STA, CRD, BLQ, ATL and ABB the way Bernese reads them. "
        "Reads only; writes nothing. Inside a planned run the same findings appear "
        "in `bernese-run-year --plan` as PROBLEM and WARNING lines."
    )
    ap.add_argument("--sta", type=Path, required=True, help="station information file (.STA)")
    ap.add_argument("--crd", type=Path, help="coordinate file (.CRD)")
    ap.add_argument("--blq", type=Path, help="ocean loading file (.BLQ)")
    ap.add_argument("--atl", type=Path, help="atmospheric loading file (.ATL)")
    ap.add_argument("--abb", type=Path, help="abbreviation file (.ABB); missing lines only warn")
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
        files = {k: load(getattr(args, k)) for k in ("crd", "blq", "atl", "abb")}
    except OSError as e:
        print(f"cannot read: {e}", file=sys.stderr)
        return 2
    coverage = scan(args.rinex_dir, args.year) if args.rinex_dir else None
    findings = check_station_files(
        sta=sta,
        **files,
        coverage=coverage,
        days=range(args.doy_from, args.doy_to + 1),
        year=args.year,
    )
    files_given = (args.crd, args.blq, args.atl, args.abb)
    checked = [args.sta.name] + [p.name for p in files_given if p]
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
