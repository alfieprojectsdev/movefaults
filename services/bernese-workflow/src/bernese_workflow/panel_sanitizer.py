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
import shutil
from dataclasses import dataclass, field
from pathlib import Path

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


# The ADDNEQ2 MAXPAR value line: `MAXPAR 1  "5000"`. Anchored to the line start so
# it never matches `MSG_MAXPAR ...`. Group 2 is the current integer value.
_MAXPAR_RE = re.compile(r'^(MAXPAR\s+\d+\s+")(\d+)(")', re.MULTILINE)


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
) -> ProvisionReport:
    """Provision a Bernese OPT panel tree from a repo gold-standard into ``$U/OPT``.

    Wires the sanitizer into the copy path so no un-sanitized panel reaches ``$U``:

    - ``*.INP`` panels are separator-sanitized on the way out. ``ADDNEQ2.INP`` also
      gets ``MAXPAR`` sized from *n_stations* (via ``compute_maxpar``) when given.
    - Any OTHER file (notably ``*.pl`` scripts) is copied **verbatim** — never
      separator-converted, since a Perl backslash is an escape, not a path.
    - Residual warnings the sanitizer only flags (foreign drive-letter paths,
      hardcoded session/date literals) are collected per file. With *strict* (the
      default) a panel carrying any such warning raises ``ValueError`` instead of
      being written — those must be remapped by hand before they can be gold-standard.

    Directory structure under *src_dir* is preserved under *dest_dir*.
    """
    from .backends import compute_maxpar

    src = Path(src_dir).expanduser()
    dest = Path(dest_dir).expanduser()
    report = ProvisionReport()

    for path in sorted(p for p in src.rglob("*") if p.is_file()):
        rel = path.relative_to(src)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)

        if path.suffix.upper() != ".INP":
            shutil.copy2(path, target)          # scripts etc. — verbatim
            report.written.append(target)
            continue

        result = sanitize_panel_text(path.read_text(encoding="ascii", errors="replace"))
        out_text = result.text
        if path.name.upper() == "ADDNEQ2.INP" and n_stations is not None:
            out_text, _ = set_addneq2_maxpar(out_text, compute_maxpar(n_stations))

        if result.warnings:
            report.warnings[str(rel)] = result.warnings
            if strict:
                offenders = ", ".join(
                    f"L{w.line} {w.kind}" for w in result.warnings
                )
                raise ValueError(
                    f"{rel}: panel carries unresolved hazards, refusing to provision "
                    f"(remap by hand first): {offenders}"
                )

        target.write_text(out_text, encoding="ascii")
        report.written.append(target)

    return report
