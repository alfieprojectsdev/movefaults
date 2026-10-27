"""Plan a multi-day run before any of it starts: which days, in which blocks,
and what to check first.

WHY THIS EXISTS
Every exclusion and preflight in scripts/run_phref_year.sh was learned from a
failed BPE run, minutes or hours in:

* Days with fewer than three reference stations cannot be tied to the frame
  (Helmert needs three). LUZON 2025 lost six days that way, each discovered by
  failing. The scripts carry the result as a hand-kept list
  (PHREF_EXCLUDE="058 059 060 061 345"), and SETTLED.md records why a list is
  wrong: LUZON's was copied to PHREF and was wrong for it.
* A dangling WAIT= or NEXTJOB= breaks the BPE when that step is reached.
* MAXPAR too small failed 24 of 24 days on 29 August. The single test day had
  33 stations; the busiest day had 41.

This module derives the list instead of keeping it: the reference set is the
PCF's V_REFINF .FIX file, and which of those stations have data on each day is
read from the campaign's datapool directory. On PHREF 2025 that gives exactly
058-061 and 345.

MAXPAR IS REPORTED, NOT CHECKED
The cutover plan asks for "the parameter count against the panel's MAXPAR".
The parameter count is not known: docs/bernese_maxpar_limit.md withdrew its
per-station estimate, and all that is measured is (1000, 3000) for a 33-41
station day. A pass/fail against a guessed number would certify configurations
nobody has run. So the plan prints every ADDNEQ2 MAXPAR the PCF uses next to
the busiest day's station count, and names the busiest day as the preflight:
run it first, and the real requirement is tested on the worst case rather than
an arbitrary one.

Nothing here runs Bernese or writes anything.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from pogf_geodetic_suite.qc.completeness import Coverage, days_in_year, scan

from .month_driver import fin_banked, session_for
from .panel_sanitizer import find_dangling_jumps, find_dangling_waits

MIN_REFERENCES = 3

# 5.4: `V_REFINF = IGS20;   DESCRIPTION=...`
_VAR54_RE = r"^{name}\s*=\s*([^;]*);"
# A .FIX station line: 4-character code, a blank, then the DOMES number or name.
_FIX_LINE_RE = re.compile(r"^([A-Z0-9]{4}) ")
# PCF process line: PID, script, option directory.
_PCF_PROCESS_RE = re.compile(r"^\d{3}\s+\S+\s+(\S+)")
_PCF_TABLE_END_RE = re.compile(r"^(PID\s+USER\b|VARIABLE\b)")
_MAXPAR_RE = re.compile(r'^MAXPAR\s+\d+\s+"(\d+)"', re.MULTILINE)


@dataclass(frozen=True)
class Excluded:
    doy: int
    reason: str  # solved | short | listed
    detail: str = ""


@dataclass
class RunPlan:
    year: int
    todo: list[int]
    excluded: list[Excluded]
    station_counts: dict[int, int] = field(default_factory=dict)
    maxpar: dict[str, int | None] = field(default_factory=dict)  # option dir -> value
    problems: list[str] = field(default_factory=list)  # each one blocks the run

    @property
    def blocks(self) -> list[tuple[int, int]]:
        return contiguous_blocks(self.todo)

    @property
    def busiest(self) -> int | None:
        """The day to run first: most stations with data; the earliest on a tie."""
        counted = [d for d in self.todo if d in self.station_counts]
        if not counted:
            return None
        return max(counted, key=lambda d: (self.station_counts[d], -d))

    @property
    def run_order(self) -> list[int]:
        """The busiest day first as the preflight, then the rest in order."""
        b = self.busiest
        return self.todo if b is None else [b] + [d for d in self.todo if d != b]

    @property
    def ok(self) -> bool:
        return not self.problems


def contiguous_blocks(days: Iterable[int]) -> list[tuple[int, int]]:
    """Runs of consecutive days as (first, last).

    BSW's multi-session mode runs N consecutive sessions from a start and cannot
    skip one, so every excluded day becomes a block boundary.
    """
    out: list[tuple[int, int]] = []
    for d in sorted(set(days)):
        if out and d == out[-1][1] + 1:
            out[-1] = (out[-1][0], d)
        else:
            out.append((d, d))
    return out


def pcf_variable(pcf_text: str, name: str) -> str | None:
    """A PCF variable's default value, in either dialect, or None if absent.

    5.4 writes `V_X = value;`. 5.2 has a fixed-column table whose value column
    starts where the header's DEFAULT does.
    """
    m = re.search(_VAR54_RE.format(name=re.escape(name)), pcf_text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    col = None
    for line in pcf_text.splitlines():
        line = line.rstrip("\r")
        if line.startswith("VARIABLE") and "DEFAULT" in line:
            col = line.index("DEFAULT")
        elif col is not None and line.split(" ", 1)[0] == name:
            return line[col:].strip()
    return None


_BSW_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand_bsw_path(value: str, env: Mapping[str, str], year: int) -> str | None:
    """Expand a PCF path the way the BPE does for the parts this needs.

    ${X} comes from ``env``; $Y+0 is the four-digit year. Anything else
    left with a $ (another offset, an unset variable) gives None rather than a
    guessed path.
    """
    out = value.replace("$Y+0", f"{year:04d}")
    out = _BSW_ENV_RE.sub(lambda m: env.get(m.group(1), m.group(0)), out)
    return None if "$" in out else out


def _pcf_dir(
    pcf_text: str, name: str, env: Mapping[str, str], year: int, fallback: Path
) -> tuple[Path, str]:
    value = pcf_variable(pcf_text, name)
    if value is None:
        return fallback, f"fallback ({name} not in the PCF)"
    expanded = expand_bsw_path(value, env, year)
    if expanded is None:
        return fallback, f"fallback ({name} = {value} could not be expanded)"
    return Path(expanded), f"from {name} = {value}"


def rinex_dir(pcf_text: str, env: Mapping[str, str], year: int, fallback: Path) -> tuple[Path, str]:
    """The datapool directory the PCF reads RINEX from (V_RNXDIR), and where that came from.

    Not $D/<campaign>: LZFLT reads LUZON's data, and RNX2SNX reads ${D}/RINEX.
    """
    return _pcf_dir(pcf_text, "V_RNXDIR", env, year, fallback)


def result_dir(
    pcf_text: str, env: Mapping[str, str], year: int, fallback: Path
) -> tuple[Path, str]:
    """The SAVEDISK directory the PCF archives to (V_RESULT, year expanded); SOL/ is under it.

    Not $S/<campaign>/<year>: EXAMPLE's RNX2SNX.PCF archives to ${S}/RNX2SNX/$Y+0.
    """
    return _pcf_dir(pcf_text, "V_RESULT", env, year, fallback)


def fix_stations(fix_text: str) -> set[str]:
    """Station codes in a Bernese .FIX file (the reference set)."""
    return {m.group(1) for line in fix_text.splitlines() if (m := _FIX_LINE_RE.match(line))}


def pcf_option_dirs(pcf_text: str) -> list[str]:
    """Option directories named in the PCF's process table, in first-use order."""
    seen: list[str] = []
    for line in pcf_text.splitlines():
        s = line.strip()
        if _PCF_TABLE_END_RE.match(s):
            break
        m = _PCF_PROCESS_RE.match(s)
        if m and m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def addneq2_maxpar(opt_root: Path, option_dirs: Iterable[str]) -> dict[str, int | None]:
    """MAXPAR of every ADDNEQ2.INP among the option directories (None: no MAXPAR line)."""
    out: dict[str, int | None] = {}
    for d in option_dirs:
        p = opt_root / d / "ADDNEQ2.INP"
        if p.is_file():
            m = _MAXPAR_RE.search(p.read_text(errors="replace"))
            out[d] = int(m.group(1)) if m else None
    return out


def check_pcf(pcf_text: str) -> list[str]:
    """Dangling WAIT and jump references, as problems that block the run."""
    problems = [
        f"PCF line {w.line}: WAIT names {w.pid}, which is not defined"
        for w in find_dangling_waits(pcf_text)
    ]
    problems += [
        f"PCF line {j.line}: {j.keyword} names {j.pid or '(empty)'}, which is not defined"
        for j in find_dangling_jumps(pcf_text).dangling
    ]
    return problems


def fin_present(sol_dir: Path, year: int, doy: int, session_char: str = "0") -> bool:
    """scripts/' test for a solved day: any FIN_<year><session>.* file.

    Deliberately as broad as scripts/' `ls FIN_*`: it also matches a reference
    copy such as FIN_20230110.SNX.gz_REF, so --done fin keeps parity with them.
    """
    return any(sol_dir.glob(f"FIN_{year}{session_for(doy, session_char)}.*"))


def build_plan(
    year: int,
    doy_from: int,
    doy_to: int,
    *,
    done: Callable[[int], bool],
    coverage: Coverage | None,
    references: Iterable[str],
    min_references: int = MIN_REFERENCES,
    listed: Mapping[int, str] | None = None,
) -> RunPlan:
    """Decide which days in [doy_from, doy_to] to run.

    A day is excluded when it is already done, when it is listed by hand (with
    the reason), or when fewer than ``min_references`` reference stations have
    data that day. A day with no data at all is short. Order of precedence is
    that order: a solved day is reported as solved even if it is also short.

    ``coverage`` None skips the reference check and says so as a problem: a plan
    that never looked at the data must not read as one that found it complete.
    """
    last = days_in_year(year)
    if not 1 <= doy_from <= doy_to <= last:
        raise ValueError(f"day range {doy_from}-{doy_to} is not within 1-{last} of {year}")
    refs = {r.upper() for r in references}
    listed = dict(listed or {})
    plan = RunPlan(year=year, todo=[], excluded=[])
    if coverage is None:
        plan.problems.append("no datapool scan: reference-station coverage was not checked")
    elif not refs:
        plan.problems.append("empty reference set: reference-station coverage was not checked")

    for doy in range(doy_from, doy_to + 1):
        if coverage is not None:
            plan.station_counts[doy] = len(coverage.by_day.get(doy, set()))
        if done(doy):
            plan.excluded.append(Excluded(doy, "solved"))
        elif doy in listed:
            plan.excluded.append(Excluded(doy, "listed", listed[doy]))
        elif coverage is not None and refs:
            present = sorted(coverage.by_day.get(doy, set()) & refs)
            if len(present) < min_references:
                detail = f"{len(present)} reference station(s)" + (
                    f": {' '.join(present)}" if present else ""
                )
                plan.excluded.append(Excluded(doy, "short", detail))
            else:
                plan.todo.append(doy)
        else:
            plan.todo.append(doy)
    return plan


def format_plan(plan: RunPlan, *, label: str = "") -> str:
    """The plan as text, laid out like run_phref_year.sh --plan so the two diff."""
    lines = [f"year {plan.year}" + (f"   {label}" if label else "")]
    for a, b in plan.blocks:
        lines.append(f"  DOY {a:03d}-{b:03d}  ({b - a + 1} days)")
    lines.append(f"  total to process: {len(plan.todo)} days")
    by_reason: dict[str, list[Excluded]] = {}
    for e in plan.excluded:
        by_reason.setdefault(e.reason, []).append(e)
    lines.append(f"  already solved and kept: {len(by_reason.get('solved', []))}")
    for e in by_reason.get("short", []) + by_reason.get("listed", []):
        lines.append(f"  excluded DOY {e.doy:03d}  {e.reason}: {e.detail}")
    first = plan.busiest
    if first is not None:
        lines.append(
            f"  preflight: DOY {first:03d} first, the busiest day "
            f"({plan.station_counts[first]} stations)"
        )
    for d, v in plan.maxpar.items():
        lines.append(f"  ADDNEQ2 MAXPAR {d}: {v if v is not None else 'no MAXPAR line'}")
    for p in plan.problems:
        lines.append(f"  PROBLEM: {p}")
    return "\n".join(lines)


def _env_path(name: str) -> Path:
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"${name} is not set; source LOADGPS.setvar first")
    return Path(v)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plan a multi-day BPE run. Runs nothing.")
    ap.add_argument("--campaign", required=True, help="campaign name, e.g. PHREF")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--pcf", required=True, help="PCF name without .PCF, e.g. PHREF_DLY")
    ap.add_argument("--from", dest="doy_from", type=int, default=1)
    ap.add_argument("--to", dest="doy_to", type=int, default=None)
    ap.add_argument("--min-references", type=int, default=MIN_REFERENCES)
    ap.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="DOY:REASON",
        help="exclude a day by hand, with the reason; repeatable",
    )
    ap.add_argument(
        "--done",
        choices=("banked", "fin"),
        default="banked",
        help="banked: FIN plus the service's .done marker (default). "
        "fin: any FIN_* file, as scripts/ decides",
    )
    ap.add_argument("--session-char", default="0")
    args = ap.parse_args(argv)

    u, d, s = _env_path("U"), _env_path("D"), _env_path("S")
    pcf_path = u / "PCF" / f"{args.pcf}.PCF"
    pcf_text = pcf_path.read_text(errors="replace")
    listed = {}
    for item in args.exclude:
        doy, _, reason = item.partition(":")
        listed[int(doy)] = reason or "excluded by hand"

    problems: list[str] = []
    refinf = pcf_variable(pcf_text, "V_REFINF")
    refs: set[str] = set()
    if not refinf:
        problems.append(f"{pcf_path.name} has no V_REFINF: the reference set is unknown")
    else:
        fix = d / "REF54" / f"{refinf}.FIX"
        try:
            refs = fix_stations(fix.read_text(errors="replace"))
        except OSError as exc:
            problems.append(f"cannot read the reference set {fix}: {exc}")

    env = {**os.environ, "D": str(d), "S": str(s), "U": str(u)}
    datadir, data_from = rinex_dir(pcf_text, env, args.year, fallback=d / args.campaign)
    print(f"datapool: {datadir}  ({data_from})")
    coverage = scan(datadir, args.year) if datadir.is_dir() else None
    if coverage is None:
        problems.append(f"no datapool directory {datadir}")

    resdir, res_from = result_dir(
        pcf_text, env, args.year, fallback=s / args.campaign / str(args.year)
    )
    sol = resdir / "SOL"
    print(f"results:  {sol}  ({res_from})")
    sc = args.session_char
    done = (
        (lambda doy: fin_banked(sol, args.year, doy, sc))
        if args.done == "banked"
        else (lambda doy: fin_present(sol, args.year, doy, sc))
    )
    plan = build_plan(
        args.year,
        args.doy_from,
        args.doy_to or days_in_year(args.year),
        done=done,
        coverage=coverage,
        references=refs,
        min_references=args.min_references,
        listed=listed,
    )
    plan.problems[:0] = problems
    plan.problems += check_pcf(pcf_text)
    plan.maxpar = addneq2_maxpar(u / "OPT", pcf_option_dirs(pcf_text))
    print(
        format_plan(
            plan,
            label=f"PCF {args.pcf}   references {refinf} ({len(refs & set(coverage.stations if coverage else []))} with data)",
        )
    )
    return 0 if plan.ok else 1


if __name__ == "__main__":
    sys.exit(main())
