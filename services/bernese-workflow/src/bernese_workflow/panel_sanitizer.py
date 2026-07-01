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

import re
from dataclasses import dataclass, field

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

# PCF process line: a 3-digit PID at the start of the line.
_PCF_PID_RE = re.compile(r"^(\d{3})\s+\S+")
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

    # splitlines() drops a trailing newline; restore it if the input had one.
    result_text = "\n".join(out_lines)
    if text.endswith("\n"):
        result_text += "\n"

    return SanitizeResult(text=result_text, warnings=warnings, changed=changed)


def find_dangling_waits(pcf_text: str) -> list[DanglingWait]:
    """Return WAIT dependencies that reference an undefined PID.

    A dangling WAIT makes the BPE block forever on a process that will never run
    (the exact hazard behind the stray ``WAIT=522`` dropped from PAGENET.PCF).
    """
    defined: set[str] = set()
    for raw in pcf_text.splitlines():
        m = _PCF_PID_RE.match(raw.strip())
        if m:
            defined.add(m.group(1))

    dangling: list[DanglingWait] = []
    for i, raw in enumerate(pcf_text.splitlines(), start=1):
        stripped = raw.strip()
        if _is_comment(stripped):
            continue
        for wm in _PCF_WAIT_RE.finditer(stripped):
            for pid in wm.group(1).split():
                if pid not in defined:
                    dangling.append(DanglingWait(i, pid))
    return dangling
