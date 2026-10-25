"""
Sanitize Bernese OPT/*.INP panels for Linux + orchestration (RH-004, gaps #8/#14).

Panels authored on Windows and copied onto the Linux BPE carry three portability
hazards seen verbatim in the NAMRIA training week's ``PGN_WK`` panels:

1. Backslash path separators inside otherwise-Bernese paths
   (``"${P}/SOB\\GEN\\SESSIONS.SES"``) — literal characters on Linux.
2. Absolute Windows drive-letter install paths (``"C:\\Bernese\\GPSUSER54\\"``) —
   these are not just wrong separators; they point at a Windows install tree that
   does not exist on the R740. Converting the separators would produce a still-
   broken ``C:/Bernese/...`` path and *mask* the real problem.
3. Hardcoded session/date literals baked in from whoever last saved the panel
   (``"$(FIN)_20261030.NQ0"``, ``SESSION_YEAR 1 "2026"``, ``STADAT 1 "2026 04 14"``)
   — a per-session run must not carry another session's frozen dates.

Design contract: **convert only what is safe; flag everything else.** Mixed
Bernese/Windows separators are converted; foreign absolute paths and hardcoded
session/date literals are reported as warnings and left untouched, so a human or
the orchestrator remaps them deliberately rather than silently shipping a broken
panel.

SCOPE: INP panel text only. Do NOT run separator conversion on ``SCRIPT/*.pl`` —
a backslash in Perl is an escape, not a path separator, and blanket conversion
would corrupt the script.
"""
from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# A double-quoted value on a panel line: SESSION_TABLE 1  "<value>"
_QUOTED_RE = re.compile(r'"([^"]*)"')

# Windows drive-letter absolute path, e.g. C:\Bernese\... or D:/foo
_DRIVE_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")

# A YYYYDDD(s) session stamp embedded in a filename: ..._20261030.NQ0
# 7 digits = year(4) + day-of-year(3); an optional 8th = session character.
_SESSION_STAMP_RE = re.compile(r"_(\d{7,8})\.")

# Panel directives that carry a frozen processing date/year.
_DATE_DIRECTIVES = ("SESSION_YEAR", "YR4_INFO", "STADAT", "ENDDAT", "SESSION_DOY")
_DATE_DIRECTIVE_RE = re.compile(r"^(" + "|".join(_DATE_DIRECTIVES) + r")\b")

# A literal campaign name under ${P}, e.g. "${P}/SOB" or "${P}/SOB/GEN/...".
# $P is the campaign ROOT, so anything naming a campaign directly is pinned to
# whichever campaign the panel was captured from. The real PGN_WK/MENU.INP came
# across carrying "${P}/SOB" — the instructor's demo campaign — in both
# ACTIVE_CAMPAIGN and SESSION_TABLE. That is a directory which does not exist on
# the R740, and neither line matched any existing hazard class: the backslashes
# were auto-converted and the panel then reported clean. PR #65's PROVENANCE.md
# listed it as "expect the provisioner to catch this"; it did not.
_HARDCODED_CAMPAIGN_RE = re.compile(r"\$\{?P\}?/([A-Za-z_][A-Za-z0-9_]*)")

# PCF process line: a 3-digit PID at the start of the line.
_PCF_PID_RE = re.compile(r"^(\d{3})\s+\S+")
# Where the process table ends: 5.2's special-actions header, or the variable
# table header (both dialects). Rows below it can start with a PID-shaped column
# (`201                       $201`) but they define no process, and reading them
# as definitions would let a reference to a deleted process pass as defined.
_PCF_PROCESS_TABLE_END_RE = re.compile(r"^(PID\s+USER\b|VARIABLE\b)")
# WAIT dependency list, terminated by ';' or end of line.
_PCF_WAIT_RE = re.compile(r"WAIT=([\d ]+)")


@dataclass
class PanelWarning:
    """A hazard the sanitizer refuses to auto-fix — needs deliberate remap."""

    line: int          # 1-indexed source line
    kind: str          # "foreign_abs_path" | "hardcoded_session" | "hardcoded_date"
    text: str          # the offending line, stripped


@dataclass
class SanitizeResult:
    text: str                                       # separator-converted panel text
    warnings: list[PanelWarning] = field(default_factory=list)
    changed: bool = False                           # any separator conversion applied

    @property
    def ok(self) -> bool:
        """True when nothing needs human attention (no warnings)."""
        return not self.warnings


@dataclass
class DanglingWait:
    line: int          # 1-indexed line of the WAIT
    pid: str           # referenced PID with no matching process definition


def _is_comment(stripped: str) -> bool:
    return stripped.startswith("#")


def _convert_separators_in_quotes(line: str) -> tuple[str, bool]:
    """Convert ``\\``→``/`` only inside quoted values that are *mixed* Bernese
    paths (already contain ``/`` or a ``${VAR}``). Leaves pure drive-letter paths
    and non-path strings alone. Returns (new_line, changed)."""
    changed = False

    def _repl(m: re.Match[str]) -> str:
        nonlocal changed
        val = m.group(1)
        if "\\" not in val:
            return m.group(0)
        # Only touch values that are recognisably Bernese-relative paths.
        looks_like_bernese_path = "/" in val or "${" in val
        if not looks_like_bernese_path:
            return m.group(0)          # e.g. "C:\Bernese\..." — flagged elsewhere
        if _DRIVE_ABS_RE.match(val):
            return m.group(0)          # defensive: never convert a drive path
        changed = True
        return '"' + val.replace("\\", "/") + '"'

    return _QUOTED_RE.sub(_repl, line), changed


def sanitize_panel_text(text: str) -> SanitizeResult:
    """Sanitize one Bernese INP panel.

    Converts mixed Bernese/Windows path separators; flags foreign absolute paths
    and hardcoded session/date literals without altering them.
    """
    out_lines: list[str] = []
    warnings: list[PanelWarning] = []
    changed = False

    for i, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()

        # 1. Separator conversion (safe, on every line's quoted values).
        new_line, line_changed = _convert_separators_in_quotes(raw)
        changed = changed or line_changed
        out_lines.append(new_line)

        # Flagging is skipped for comment / box-drawing lines.
        if _is_comment(stripped):
            continue

        for m in _QUOTED_RE.finditer(new_line):
            val = m.group(1)
            # 2. Foreign absolute (drive-letter) path.
            if _DRIVE_ABS_RE.match(val):
                warnings.append(PanelWarning(i, "foreign_abs_path", stripped))
            # 3a. Hardcoded session stamp in a filename.
            if _SESSION_STAMP_RE.search(val):
                warnings.append(PanelWarning(i, "hardcoded_session", stripped))

        # 3b. Hardcoded processing date/year directive.
        if _DATE_DIRECTIVE_RE.match(stripped):
            warnings.append(PanelWarning(i, "hardcoded_date", stripped))

        for qm in _QUOTED_RE.finditer(stripped):
            if _HARDCODED_CAMPAIGN_RE.search(qm.group(1)):
                warnings.append(PanelWarning(i, "hardcoded_campaign", stripped))
                break

    # splitlines() drops a trailing newline; restore it if the input had one.
    result_text = "\n".join(out_lines)
    if text.endswith("\n"):
        result_text += "\n"

    return SanitizeResult(text=result_text, warnings=warnings, changed=changed)


# The 5.2 columnar process row:  `511 ADDNEQ2   R2S_FIN   ANY   1 502 503`
# PID, SCRIPT, OPT_DIR, CPU, F, then a bare space-separated WAIT list. There is
# no `WAIT=` keyword anywhere in this dialect.
_PCF_ROW_COLUMNAR_RE = re.compile(
    r"^(\d{3})\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)(?:\s+([\d\s]+?))?\s*$"
)


def _defined_pids(lines: list[str]) -> set[str]:
    """PIDs defined in the process table, and only there."""
    defined: set[str] = set()
    for raw in lines:
        stripped = raw.strip()
        if _PCF_PROCESS_TABLE_END_RE.match(stripped):
            break
        m = _PCF_PID_RE.match(stripped)
        if m:
            defined.add(m.group(1))
    return defined


def find_dangling_waits(pcf_text: str) -> list[DanglingWait]:
    """Return WAIT dependencies that reference an undefined PID.

    A dangling WAIT makes the BPE block forever on a process that will never run
    (the hazard behind the stray ``WAIT=522`` dropped from PAGENET.PCF).

    TWO PCF DIALECTS, and missing the second one made this function useless
    exactly when it mattered (2026-08-05):

    * **keyword** — ``501 GPSCLUAP R2S_FIN CPU=ANY; WAIT=499`` (Bernese 5.4)
    * **columnar** — ``511 ADDNEQ2  R2S_FIN  ANY  1 502`` (PHIVOLCS 5.2), where
      the WAIT list is a bare trailing column with no keyword at all.

    Until this was fixed the function matched only ``WAIT=``, so on a 5.2 PCF it
    found **zero** WAITs, concluded **zero** dangling, and returned a clean
    report having inspected nothing. That report was used to sign off
    ``LUZON_DLY.PCF``, which then failed at runtime on the very first process:
    ``001: R2S_COP — Invalid PID: 000``. Four of its WAIT lists were broken.

    A checker that silently does not understand its input is worse than no
    checker, because it converts "unverified" into "verified".
    """
    lines = pcf_text.splitlines()
    defined = _defined_pids(lines)

    dangling: list[DanglingWait] = []
    for i, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if _PCF_PROCESS_TABLE_END_RE.match(stripped):
            break                       # no WAIT lists below the process table
        if _is_comment(stripped):
            continue

        found_keyword = False
        for wm in _PCF_WAIT_RE.finditer(stripped):
            found_keyword = True
            for pid in wm.group(1).split():
                if pid not in defined:
                    dangling.append(DanglingWait(i, pid))
        if found_keyword:
            continue

        # Columnar dialect. Only consider rows that actually look like process
        # rows, so variable/parameter tables are not misread as dependencies.
        cm = _PCF_ROW_COLUMNAR_RE.match(stripped)
        if cm and cm.group(6):
            for pid in cm.group(6).split():
                if pid not in defined:
                    dangling.append(DanglingWait(i, pid))
    return dangling


# Jump targets, in both dialects, read as BSW 5.4 reads them (P_BPE.f90).
#   5.4 keyword:  `011  RNX_COP  R2S_GEN  CPU=ANY; WAIT=001;  NEXTJOB= 099 999`
#                 `022  CCRNXO_P R2S_GEN  CPU=ANY; WAIT=021;  PARALLEL=021`
#     The value runs to the next `;` and every token is looked up verbatim as a
#     PID (job_findPID): `$301` is not PID 301. NEXTJOB takes a list, `_` being
#     an empty slot; PARALLEL takes exactly one PID.
#   5.2 special-actions table, after the process table:
#                 `331                       NEXTJOB  301`
#                 `201                       $201`
#                 `211                       PARALLEL $201`
#     Fixed width, `(I3,1X,A12,1X,A8,9(1X,A8))`, and a keyword only counts in
#     PARAM1. `PARALLEL $201` names no PID: BSW finds the job whose PARAM1 is
#     the label `$201` among the rows it has already read, and uses that job
#     (pcf_updateParalleJob_V0). Only PARAM2 is read after PARALLEL.
# A token that is not a defined PID (`31`, `3011`, a variable) is reported,
# never skipped, so a typo cannot pass as clean.
_PCF_JUMP_KEYWORD_RE = re.compile(r"\b(NEXTJOB|PARALLEL)=([^;]*)")
_PCF_JUMP_KEYWORDS = ("NEXTJOB", "PARALLEL")
_PCF_JUMP_WORD_RE = re.compile(r"\b(NEXTJOB|PARALLEL)\b(?!=)")
_PCF_SPECIAL_TABLE_RE = re.compile(r"^PID\s+USER\b")
_PCF_VARIABLE_TABLE_RE = re.compile(r"^VARIABLE\b")
_PCF_SPECIAL_ROW_RE = re.compile(r"^(\d{3})\s")
# 5.2 parameter-row special actions that are not jumps and carry no label.
_PCF_52_NON_LABEL = ("SKIP", "CONT_ERR")


def _special_row_params(raw: str) -> list[str]:
    """PARAM1..PARAM9 of a 5.2 special-actions row, by BSW's column layout."""
    line = raw.rstrip("\r\n")
    return [line[26 + 9 * k: 34 + 9 * k].strip() for k in range(9)]


@dataclass
class DanglingJump:
    line: int          # 1-indexed line of the reference
    keyword: str       # NEXTJOB or PARALLEL
    pid: str           # referenced PID (or a 5.2 special-action row's own PID)
                       # with no process definition; may be a malformed token,
                       # verbatim. A 5.2 PARALLEL label is reported without `$`;
                       # a 5.2 keyword outside PARAM1 reports what PARAM1 holds


@dataclass
class JumpCheck:
    checked: int                 # references inspected; see find_dangling_jumps
    dangling: list[DanglingJump]


def find_dangling_jumps(pcf_text: str) -> JumpCheck:
    """Return NEXTJOB and PARALLEL references to an undefined PID.

    The companion to ``find_dangling_waits``, for the plan-phase check "finds
    dangling WAIT= and NEXTJOB= in the PCF". NEXTJOB names the processes a script
    may jump to; PARALLEL names the process whose file list a job is split over.
    Either one naming a PID that does not exist breaks the BPE when the jump is
    taken, which can be hours into a run. Both dialects are read: the 5.4
    keywords on the process line, and the 5.2 special-actions table.

    ``checked`` comes back with the result for the reason recorded on
    ``find_dangling_waits``: an empty list from a function that matched nothing
    is not a clean bill. A PCF that uses NEXTJOB or PARALLEL and gives
    ``checked == 0`` was not understood.
    """
    lines = pcf_text.splitlines()
    defined = _defined_pids(lines)

    checked = 0
    dangling: list[DanglingJump] = []
    in_special = False
    labels: dict[str, list[str]] = {}   # 5.2 PARAM1 label -> owners, read so far

    def check(i: int, keyword: str, pid: str) -> None:
        nonlocal checked
        checked += 1
        if pid not in defined:
            dangling.append(DanglingJump(i, keyword, pid))

    for i, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if _PCF_VARIABLE_TABLE_RE.match(stripped):
            break                       # no jumps in the variable table
        if _PCF_SPECIAL_TABLE_RE.match(stripped):
            in_special = True
            continue
        if _is_comment(stripped):
            continue

        if in_special:
            sm = _PCF_SPECIAL_ROW_RE.match(raw)
            if not sm:
                continue
            owner = sm.group(1)
            params = _special_row_params(raw)
            keyword = params[0]
            if keyword not in _PCF_JUMP_KEYWORDS:
                if (wm := _PCF_JUMP_WORD_RE.search(raw[4:])):
                    # BSW reads a jump only from PARAM1; one anywhere else is a
                    # broken jump, not an absent one.
                    checked += 1
                    dangling.append(DanglingJump(i, wm.group(1), keyword))
                elif keyword and keyword not in _PCF_52_NON_LABEL and owner in defined:
                    labels.setdefault(keyword, []).append(owner)
                continue
            # A special action attaches to the process in its first column; one
            # left behind for a deleted process is as broken as a bad target.
            check(i, keyword, owner)
            if keyword == "NEXTJOB":
                for token in " ".join(params[1:]).split():
                    if token != "_":
                        check(i, keyword, token)
            elif params[1]:
                owners = labels.get(params[1])
                checked += 1
                if owners:
                    owners.pop(0)       # BSW consumes the label when it matches
                else:
                    dangling.append(DanglingJump(i, keyword, params[1].removeprefix("$")))
            continue

        for keyword, targets in (m.groups() for m in _PCF_JUMP_KEYWORD_RE.finditer(stripped)):
            tokens = targets.split()
            if keyword == "PARALLEL":
                # An empty PARALLEL= is no special action at all; anything else
                # is looked up as one PID, spaces included.
                if tokens:
                    check(i, keyword, " ".join(tokens))
                continue
            # `_` is a placeholder slot, and an empty list is no jump at all
            # (stock CLKDET's GOTO rows). Neither is a reference.
            for token in tokens:
                if token != "_":
                    check(i, keyword, token)
    return JumpCheck(checked, dangling)


# The ADDNEQ2 MAXPAR value line: `MAXPAR 1  "5000"`. Anchored to the line start so
# it never matches `MSG_MAXPAR ...`. Group 2 is the current integer value.
_MAXPAR_RE = re.compile(r'^(MAXPAR\s+\d+\s+")(\d+)(")', re.MULTILINE)


def _current_addneq2_maxpar(text: str) -> int | None:
    """The MAXPAR currently in the panel, or None if it has no MAXPAR line."""
    m = _MAXPAR_RE.search(text)
    return int(m.group(2)) if m else None


def set_addneq2_maxpar(text: str, value: int) -> tuple[str, bool]:
    """Set the ADDNEQ2 ``MAXPAR`` value (readiness task B).

    Rewrites ``MAXPAR 1 "<n>"`` to *value*, leaving ``MSG_MAXPAR`` (the help text)
    untouched. Pair with ``backends.compute_maxpar(n_stations)`` so the combined-NEQ
    parameter ceiling scales with the network instead of a frozen literal (the panel
    ships hardcoded at "5000"; a ~270-station R740 run overflows it). Returns
    ``(new_text, changed)``; *changed* is False when the panel has no MAXPAR line.
    """
    if value <= 0:
        raise ValueError(f"MAXPAR must be > 0, got {value}")
    new_text, n = _MAXPAR_RE.subn(
        lambda m: f"{m.group(1)}{value}{m.group(3)}", text
    )
    return new_text, n > 0


@dataclass
class ProvisionReport:
    """Outcome of provisioning an OPT panel tree to ``$U``."""

    written: list[Path] = field(default_factory=list)
    # dest-relative panel path → residual warnings the sanitizer could not auto-fix.
    warnings: dict[str, list[PanelWarning]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not any(self.warnings.values())


def provision_opt_dir(
    src_dir: str | Path,
    dest_dir: str | Path,
    *,
    n_stations: int | None = None,
    strict: bool = True,
    dry_run: bool = False,
) -> ProvisionReport:
    """Provision a Bernese OPT panel tree from a repo gold-standard into ``$U/OPT``.

    Wires the sanitizer into the copy path so no un-sanitized panel reaches ``$U``:

    - ``*.INP`` panels are separator-sanitized on the way out. ``ADDNEQ2.INP`` also
      gets ``MAXPAR`` sized from *n_stations* (via ``compute_maxpar``) when given.
    - Any OTHER file (notably ``*.pl`` scripts) is copied **verbatim** — never
      separator-converted, since a Perl backslash is an escape, not a path.
    - Residual warnings the sanitizer only flags (foreign drive-letter paths,
      hardcoded session/date literals) are collected per file. With *strict* (the
      default) a panel carrying any such warning aborts the WHOLE provisioning with
      ``ValueError`` — those must be remapped by hand before they can be gold-standard.

    Directory structure under *src_dir* is preserved under *dest_dir*.

    Two-pass and atomic w.r.t. the strict check: everything is sanitized and all
    warnings gathered BEFORE anything is written, so a dirty panel late in the tree
    never leaves ``$U`` half-updated (no clean files written, then a raise).

    With *dry_run* the second pass is skipped entirely: the report lists what
    WOULD be written and nothing is touched. This existed only as a caller-side
    assumption before 2026-08-04 — ``scripts/provision_gpsuser.py`` printed
    "DRY RUN — nothing will be written" and then wrote every panel, because it
    had no way to ask for one. ``report.written`` is populated either way so the
    plan can be shown; consult *dry_run* to know whether it happened.
    """
    from .backends import compute_maxpar

    src = Path(src_dir).expanduser()
    dest = Path(dest_dir).expanduser()
    report = ProvisionReport()

    # Pass 1 — sanitize/plan every file and collect all warnings; write nothing yet.
    # planned entries: (target, kind, payload) where kind is "copy" (payload=src
    # path) or "write" (payload=sanitized text).
    planned: list[tuple[Path, str, Path | str]] = []
    for path in sorted(p for p in src.rglob("*") if p.is_file()):
        rel = path.relative_to(src)
        target = dest / rel

        if path.suffix.upper() != ".INP":
            planned.append((target, "copy", path))    # scripts etc. — verbatim
            continue

        result = sanitize_panel_text(path.read_text(encoding="ascii", errors="replace"))
        out_text = result.text
        if path.name.upper() == "ADDNEQ2.INP" and n_stations is not None:
            # MAXPAR is a CEILING: raise it, never lower it. compute_maxpar is a
            # rule of thumb (N*4 + 500, floored at 1000) and for a ~72-station
            # network yields 1000 — which would have overwritten the "10000" the
            # PAGENET panel carries, a value raised deliberately after a real
            # ADDNEQ2 parameter overflow during the training week. A heuristic
            # must not silently undo a fix someone made against observed
            # behaviour, so the larger of the two wins.
            wanted = compute_maxpar(n_stations)
            current = _current_addneq2_maxpar(out_text)
            if current is not None and current > wanted:
                logger.info(
                    "%s: keeping existing MAXPAR %d (computed %d would lower it)",
                    rel, current, wanted,
                )
            else:
                out_text, _ = set_addneq2_maxpar(out_text, wanted)

        if result.warnings:
            report.warnings[str(rel)] = result.warnings
        planned.append((target, "write", out_text))

    # Strict gate: abort before writing if ANY panel carries unresolved hazards.
    if strict and not report.ok:
        offenders = "; ".join(
            f"{rel}: " + ", ".join(f"L{w.line} {w.kind}" for w in ws)
            for rel, ws in report.warnings.items()
        )
        raise ValueError(
            f"refusing to provision — panels carry unresolved hazards "
            f"(remap by hand first): {offenders}"
        )

    if dry_run:
        report.written = [t for t, _, _ in planned]
        return report

    # Pass 2 — commit the planned writes.
    for target, kind, payload in planned:
        target.parent.mkdir(parents=True, exist_ok=True)
        if kind == "copy":
            assert isinstance(payload, Path)
            shutil.copy2(payload, target)
        else:
            assert isinstance(payload, str)
            target.write_text(payload, encoding="ascii")
        report.written.append(target)

    return report
