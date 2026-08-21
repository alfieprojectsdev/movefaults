"""Resolve and record the fiducial station set that defines a solution's datum.

GEO-001. A coordinate solution's datum is the least reproducible thing about
it, and until now it was the least recorded. `ADDNEQ2.INP` resolves its datum
from

    FREESTA_F 1  "${P}/PHIVOLCS\\STA\\REF190110.FIX"

and that file is not tracked in this repository. Project records disagree on
what it contains — 12 stations in one session log, 9 in a handover reply,
"6 accepted" in a third. All three may well be true of different files at
different pipeline stages, which is exactly the problem: nothing in the
pipeline records which one actually defined a given solution.

WHAT THIS MODULE DOES

Reads the resolved `.FIX` at campaign build time and produces a `FiducialSet`
carrying the path, the sha256 of the contents, and the station list. That
record is small, composable with the provenance design in
`docs/project_documentation/provenance_record_design.md`, and answers
"what defined this datum?" from the artefact rather than from memory.

WHAT IT REFUSES TO DO

Guess. If `FREESTA` selects `FROM_FILE` and the file cannot be resolved or
read, this raises. BPE's own behaviour on a missing station-selection file is
to proceed with a different datum definition, which produces coordinates that
look entirely normal and are silently on a different frame. A loud failure at
build time is worth a great deal more than a quiet one at solve time.

A NOTE ON WHAT WAS FOUND WIRING THIS UP

Of the six ADDNEQ2 panels under `config/bernese/`, **four name the same file**
— `REF190110.FIX`, 2019 day 011 (`PHI_MO`, `R2S_FIN`, `R2S_GEN`, `R2S_RED`).
`PHI_WK` names a different campaign's `REF192560.FIX`, and `PGN_WK` — in the
NAMRIA `gpsuser` tree, not the Luzon one — names `REF_20261040.FIX` under a
`./DUMMY/` path. `panel_sanitizer` already flags these as
`hardcoded_campaign`. Whether a frozen fiducial list is intended (a stable
datum, defensible) or accidental (literals nobody templated) is a PHIVOLCS
question, not an engineering one. This module does not decide it — it makes
the answer visible in every solution's record.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "FiducialSet",
    "FiducialSetError",
    "extract_freesta_reference",
    "load_fiducial_set",
    "parse_fix_file",
    "resolve_panel_path",
]

# A quoted panel value:  FREESTA_F 1  "<value>"
_PANEL_VALUE = re.compile(r'^\s*(?P<key>[A-Z0-9_]+)\s+\d+\s+"(?P<value>[^"]*)"')

# Bernese ${VAR} / $VAR path variables.
_BRACED_VAR = re.compile(r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)\}")
_BARE_VAR = re.compile(r"\$(?P<name>[A-Za-z_][A-Za-z0-9_]*)")

# A station line in a .FIX file: 4-character code, optionally followed by a
# DOMES number and/or a flag column.
_STATION_LINE = re.compile(r"^\s*(?P<name>[A-Z0-9_]{4})(?:\s+(?P<domes>\S+))?\s*(?:[A-Z])?\s*$")


class FiducialSetError(RuntimeError):
    """The datum-defining station set could not be established.

    Raised rather than returning a partial or empty set: a solution whose
    datum is unknown must not be produced quietly.
    """


@dataclass(frozen=True)
class FiducialSet:
    """The station set that defines a solution's datum, as actually resolved."""

    panel_path: Path
    """The ADDNEQ2 panel this was read from."""

    raw_reference: str
    """The FREESTA_F value verbatim, before variable expansion."""

    resolved_path: Path
    """Where raw_reference actually pointed on this machine."""

    sha256: str
    """Content hash of the .FIX file. The point of the whole record."""

    size_bytes: int

    stations: tuple[str, ...]
    """Station codes in file order."""

    @property
    def station_count(self) -> int:
        return len(self.stations)

    def to_dict(self) -> dict:
        """Shape intended for a provenance JSONL line."""
        return {
            "panel": str(self.panel_path),
            "raw_reference": self.raw_reference,
            "resolved_path": str(self.resolved_path),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "station_count": self.station_count,
            "stations": list(self.stations),
        }


def extract_freesta_reference(panel_text: str) -> tuple[str | None, str | None]:
    """Return ``(freesta_mode, freesta_file)`` from an ADDNEQ2 panel.

    Either element is None when the corresponding key is absent. The mode
    matters: ``FREESTA_F`` is only meaningful when ``FREESTA`` is
    ``FROM_FILE``, and reading it otherwise would record a datum source the
    run does not use.
    """
    mode: str | None = None
    fix_file: str | None = None
    for line in panel_text.splitlines():
        m = _PANEL_VALUE.match(line)
        if not m:
            continue
        key, value = m.group("key"), m.group("value")
        if key == "FREESTA":
            mode = value.strip()
        elif key == "FREESTA_F":
            fix_file = value.strip()
    return mode, fix_file


def resolve_panel_path(raw: str, variables: dict[str, str]) -> Path:
    """Expand Bernese path variables and normalise separators.

    Backslashes are converted the same way `panel_sanitizer` converts them —
    these panels were last saved on Windows and carry mixed separators
    (``"${P}/PHIVOLCS\\STA\\REF190110.FIX"``), which are literal characters on
    Linux.

    Raises FiducialSetError naming any variable that has no value, rather than
    leaving a literal ``${P}`` in the path to fail later as a confusing
    "no such file".
    """
    missing: list[str] = []

    def _braced(m: re.Match[str]) -> str:
        name = m.group("name")
        if name not in variables:
            missing.append(name)
            return m.group(0)
        return variables[name]

    expanded = _BRACED_VAR.sub(_braced, raw)
    expanded = _BARE_VAR.sub(_braced, expanded)

    if missing:
        raise FiducialSetError(
            f"cannot resolve {raw!r}: no value for "
            + ", ".join(f"${{{n}}}" for n in sorted(set(missing)))
        )

    return Path(expanded.replace("\\", "/"))


def parse_fix_file(path: str | Path) -> tuple[str, ...]:
    """Read station codes from a Bernese station-selection (.FIX) file.

    Bernese writes a short title/underline header, then one station per line as
    a 4-character code optionally followed by a DOMES number. Parsing is
    deliberately forgiving about the header (its exact shape varies between
    the files HELMR1 writes and the ones people hand-maintain) and strict
    about what counts as a station line.

    Raises FiducialSetError if no station lines are found — an empty fiducial
    set is not a valid datum, and silently returning () would let a solution
    proceed on an undefined frame.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise FiducialSetError(f"cannot read fiducial file {path}: {exc}") from exc

    stations: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        # Header furniture: title underlines and column rules.
        if set(line.strip()) <= {"-", "*", "="}:
            continue
        m = _STATION_LINE.match(line)
        if not m:
            continue
        name = m.group("name")
        # "STATION NAME" column headers match the 4-char shape; they are not
        # stations. Anything with a DOMES number is unambiguous.
        if name in {"STAT", "NAME", "FLAG"} and m.group("domes") is None:
            continue
        stations.append(name)

    if not stations:
        raise FiducialSetError(
            f"no station entries found in {path}. An empty fiducial set is not "
            "a datum definition; refusing to continue rather than letting BPE "
            "fall back to a different frame silently."
        )
    return tuple(stations)


def load_fiducial_set(
    panel_path: str | Path,
    variables: dict[str, str],
) -> FiducialSet | None:
    """Resolve, hash and record the fiducial set an ADDNEQ2 panel will use.

    Returns None when the panel does not define its datum from a file — that
    is a legitimate configuration (``FREESTA`` may be ``MANUAL`` or
    ``WITH_FLAG``), and there is no file to record.

    Raises FiducialSetError when the panel *does* say ``FROM_FILE`` and the
    file cannot be resolved, read, or parsed.
    """
    panel_path = Path(panel_path)
    try:
        panel_text = panel_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise FiducialSetError(f"cannot read panel {panel_path}: {exc}") from exc

    mode, raw_reference = extract_freesta_reference(panel_text)

    if mode is None:
        raise FiducialSetError(
            f"{panel_path} has no FREESTA key; this does not look like an "
            "ADDNEQ2 panel"
        )
    if mode != "FROM_FILE":
        return None
    if not raw_reference:
        raise FiducialSetError(
            f"{panel_path} sets FREESTA=FROM_FILE but FREESTA_F is empty. The "
            "datum would be undefined."
        )

    resolved = resolve_panel_path(raw_reference, variables)
    if not resolved.is_file():
        raise FiducialSetError(
            f"{panel_path} sets FREESTA=FROM_FILE pointing at {raw_reference!r}, "
            f"which resolves to {resolved} — not a readable file. BPE would "
            "proceed on a different datum definition and the coordinates would "
            "look entirely normal."
        )

    data = resolved.read_bytes()
    return FiducialSet(
        panel_path=panel_path,
        raw_reference=raw_reference,
        resolved_path=resolved,
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        stations=parse_fix_file(resolved),
    )
