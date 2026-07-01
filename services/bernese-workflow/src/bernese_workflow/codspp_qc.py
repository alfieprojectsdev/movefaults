"""
CODSPP output QC + a-priori/observation triage (RH-005, gap #9).

CODSPP (BPE jobs 301/302) is code-based single-point positioning run before the
phase solution. Its per-cluster output (``OUT/SPP_YYYYDDDs_NNN.OUT``) reports, per
station, an ``RMS OF UNIT WEIGHT`` and a coordinate correction table
(``NEW- A PRIORI``). Those two numbers separate the two failure modes a human had
to eyeball by hand during the training week:

- **Bad a priori** — high RMS *and* a large coordinate shift. The station's seed
  coordinates in the ``.CRD`` are simply wrong; CODSPP found the right position.
  Fix is free: re-seed the ``.CRD`` from the CODSPP ``NEW`` coordinates and retry.
- **Bad observations** — high RMS but a small coordinate shift. The a priori was
  fine; the data itself is bad (multipath, obstruction, receiver fault). No auto-
  fix — alert a human.

This module is the DETECTION/classification core: it parses the CODSPP output and
labels each station. The recovery ACTION (rewriting the ``.CRD`` and re-running the
BPE) is the applied layer, wired separately — see the RH-005 remainder.

Thresholds are heuristics (CODSPP code solutions sit around ~1 m RMS); they are
parameters with documented defaults and must be tuned against real network runs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_RMS_UNIT_WEIGHT_RE = re.compile(r"RMS OF UNIT WEIGHT\s*:\s*([\d.]+)")
_BAD_OBS_RE = re.compile(r"BAD OBSERVATIONS\s*:\s*([\d.]+)")
_USED_OBS_RE = re.compile(r"USED OBSERVATIONS\s*:\s*(\d+)")

# The X coordinate row carries the station code:
#   "  CUSV 21904S001    X   -1132915.14  -1132915.19  -0.05  0.01"
# columns after the axis label: A PRIORI, NEW, NEW- A PRIORI, RMS ERROR.
_COORD_X_RE = re.compile(
    r"^\s*([A-Z0-9]{4})\b.*?\bX\s+"
    r"(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)"
)
# Y and Z rows have no leading station code (label is "(MARKER)" or blank).
_COORD_YZ_RE = re.compile(
    r"\b([YZ])\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)"
)

# CODXTR combined summary:
#   "  72 FILES, MAX. RMS:    2.58 M    FOR STATION: PSRF 22032M001"
_SUMMARY_MAXRMS_RE = re.compile(
    r"MAX\.\s*RMS\s*:\s*([\d.]+)\s*M\s+FOR STATION:\s*([A-Z0-9]{4})"
)
_SUMMARY_MAXBAD_RE = re.compile(
    r"MAX\.\s*BAD\s*:\s*([\d.]+)\s*%\s+FOR STATION:\s*([A-Z0-9]{4})"
)


@dataclass
class CodsppStation:
    station: str | None
    rms_unit_weight_m: float | None
    bad_obs_pct: float | None
    used_obs: int | None
    dx: float | None  # NEW - A PRIORI, metres
    dy: float | None
    dz: float | None

    @property
    def coord_shift_m(self) -> float | None:
        """Euclidean magnitude of the a-priori correction (metres)."""
        if self.dx is None or self.dy is None or self.dz is None:
            return None
        return float((self.dx**2 + self.dy**2 + self.dz**2) ** 0.5)


def parse_codspp_output(text: str) -> CodsppStation:
    """Parse one per-cluster CODSPP ``SPP_*_NNN.OUT`` into a CodsppStation.

    Missing fields come back as None rather than raising — CODSPP output varies and
    a truncated file should degrade to "unknown", not crash the QC pass.
    """
    rms = _first_float(_RMS_UNIT_WEIGHT_RE, text)
    bad = _first_float(_BAD_OBS_RE, text)
    used_m = _USED_OBS_RE.search(text)
    used = int(used_m.group(1)) if used_m else None

    station: str | None = None
    dx = dy = dz = None
    for line in text.splitlines():
        mx = _COORD_X_RE.match(line)
        if mx:
            station = mx.group(1)
            dx = float(mx.group(4))  # NEW- A PRIORI column
            continue
        myz = _COORD_YZ_RE.search(line)
        if myz:
            delta = float(myz.group(4))
            if myz.group(1) == "Y":
                dy = delta
            else:
                dz = delta

    return CodsppStation(
        station=station,
        rms_unit_weight_m=rms,
        bad_obs_pct=bad,
        used_obs=used,
        dx=dx,
        dy=dy,
        dz=dz,
    )


def classify_codspp(
    st: CodsppStation,
    *,
    rms_threshold_m: float = 3.0,
    shift_threshold_m: float = 1.0,
) -> str:
    """Triage a CODSPP station result (gap #9).

    Returns one of:
      - ``"ok"``          — RMS within threshold.
      - ``"bad_apriori"`` — high RMS AND large coordinate shift → re-seed the .CRD
                            from the CODSPP NEW coordinates and retry (free auto-fix).
      - ``"bad_obs"``     — high RMS but small shift → data problem, alert a human.
      - ``"unknown"``     — RMS could not be parsed.

    Defaults: CODSPP code solutions normally sit near ~1 m RMS, so 3 m flags an
    outlier; a >1 m a-priori shift means the seed coordinate was materially wrong.
    Tune both against a real network before trusting unattended.
    """
    if st.rms_unit_weight_m is None:
        return "unknown"
    if st.rms_unit_weight_m <= rms_threshold_m:
        return "ok"
    shift = st.coord_shift_m
    if shift is not None and shift >= shift_threshold_m:
        return "bad_apriori"
    return "bad_obs"


@dataclass
class CodxtrSummary:
    max_rms_m: float | None
    max_rms_station: str | None
    max_bad_pct: float | None
    max_bad_station: str | None


def parse_codxtr_summary(text: str) -> CodxtrSummary:
    """Parse the combined CODXTR summary (``SPP_YYYYDDDs.OUT``) worst-station lines."""
    rms_m = _SUMMARY_MAXRMS_RE.search(text)
    bad_m = _SUMMARY_MAXBAD_RE.search(text)
    return CodxtrSummary(
        max_rms_m=float(rms_m.group(1)) if rms_m else None,
        max_rms_station=rms_m.group(2) if rms_m else None,
        max_bad_pct=float(bad_m.group(1)) if bad_m else None,
        max_bad_station=bad_m.group(2) if bad_m else None,
    )


def _first_float(pattern: re.Pattern[str], text: str) -> float | None:
    m = pattern.search(text)
    return float(m.group(1)) if m else None
