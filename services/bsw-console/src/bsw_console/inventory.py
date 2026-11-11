"""The inventory (design brief, screen 0): per station, how far a year's data has got.

One row per station, one column per step, and above them what is waiting at
each step. Read-only, like stage 1.

Connected, read from disk:
  RINEX       the campaign's datapool directory (the PCF's V_RNXDIR), by the same
              scan run_plan uses for its reference-station check
  processed   the stations each final CRD of the year estimated (fixed, or the
              float PCF's when there is one); a CRD also lists every a priori
              station unflagged, and those are not counted
  time series the span of fixed solutions across every year of the campaign, the
              files the Time series page reads (the main PCF's, not the float
              PCF's); under the time series' minimum
              span a station has no velocity worth the name

Not connected, and said so rather than guessed:
  field visit the equipment report carries no logsheet export on this server
  raw data    no catalogue of received raw files is kept
  RINEX QC    QC results are not stored, so "passed" cannot be shown
"""

from __future__ import annotations

from pathlib import Path

from bernese_workflow.run_plan import rinex_dir, sta_file
from pogf_geodetic_suite.qc.completeness import days_in_year, scan
from pogf_geodetic_suite.timeseries.crd_pipeline import read_crd_file
from pogf_geodetic_suite.timeseries.gmt import MIN_SPAN_YEARS

from .settings import Campaign, Settings
from .stations import stations_in
from .status import _pcf_text, campaign_years, year_dir

NOT_CONNECTED = {
    "field_visits": "The equipment report on this server has no logsheet export, so field visits are not known here.",
    "raw_data": "No catalogue of received raw files is kept: RAW to RINEX is still done by hand.",
    "rinex_qc": "RINEX QC results are not stored, so whether a file passed cannot be shown.",
}


# Final CRDs do not change once written (a redo writes a new file), so each is
# read once per file version: (path, mtime_ns, size) -> the codes it estimated.
_ESTIMATED: dict[tuple[str, int, int], frozenset[str]] = {}


def _estimated(p: Path) -> frozenset[str]:
    st = p.stat()
    key = (str(p), st.st_mtime_ns, st.st_size)
    if key not in _ESTIMATED:
        if len(_ESTIMATED) > 20_000:  # a bound, not a policy: years of every campaign fit
            _ESTIMATED.clear()
        _ESTIMATED[key] = frozenset(code for code, *_ in read_crd_file(p, estimated_only=True))
    return _ESTIMATED[key]


def processed_days(
    s: Settings, c: Campaign, year: int, *, include_float: bool = True
) -> dict[str, set[int]]:
    """Station code -> the DOYs whose final CRD estimated it: fixed or float, or
    fixed only (what the Time series page reads) with ``include_float=False``."""
    out: dict[str, set[int]] = {}
    pcfs = [c.pcf] + ([c.float_pcf] if c.float_pcf and include_float else [])
    for pcf in pcfs:
        sta = year_dir(s, pcf, c.name, year) / "STA"
        if not sta.is_dir():
            continue
        for p in sta.glob(f"FIN_{year}???0.CRD"):
            doy = p.name[8:11]
            if not doy.isdigit():
                continue
            try:
                codes = _estimated(p)
            except OSError:  # moved away by a redo between the glob and the read
                continue
            for code in codes:
                out.setdefault(code, set()).add(int(doy))
    return out


def _epoch(year: int, doy: int) -> float:
    return year + (doy - 0.5) / days_in_year(year)


def inventory(s: Settings, c: Campaign, year: int) -> dict:
    text = _pcf_text(s, c.pcf) or ""
    rnx, _ = rinex_dir(text, s.env, year, fallback=s.datapool / c.name)
    cov = scan(rnx, year) if Path(rnx).is_dir() else None
    rinex = {k: set(v) for k, v in (cov.by_station.items() if cov else [])}
    sta_path = sta_file(text, s.env, year, s.datapool / "REF54")
    # CRD and RINEX codes are four characters, upper case: compare the STA's the same way.
    sta_name: str | None = None
    in_sta: set[str] = set()
    if sta_path is not None and sta_path.is_file():
        sta_name = sta_path.name
        text_sta = sta_path.read_text(errors="replace")
        in_sta = {code[:4].upper() for code in stations_in("STA", text_sta)}
    sta_known = sta_name is not None
    done = processed_days(s, c, year)

    # The span the time series sees: every year of the campaign, as it reads them
    # (the main PCF's CRDs only; a float-only day is not in the series).
    first: dict[str, float] = {}
    last: dict[str, float] = {}
    for y in sorted(set(campaign_years(s, c)) | {year}):
        for code, doys in processed_days(s, c, y, include_float=False).items():
            first[code] = min(first.get(code, 9999.0), _epoch(y, min(doys)))
            last[code] = max(last.get(code, 0.0), _epoch(y, max(doys)))

    rows = []
    waiting_in_sta = waiting_not_in_sta = 0
    for code in sorted(set(rinex) | set(done)):
        r, d = rinex.get(code, set()), done.get(code, set())
        waiting = sorted(r - d)
        # An STA that cannot be read says nothing about a station: count it as waiting.
        if code in in_sta or not sta_known:
            waiting_in_sta += len(waiting)
        else:
            waiting_not_in_sta += len(waiting)
        span = round(last[code] - first[code], 2) if code in first else None
        rows.append(
            {
                "station": code,
                "in_sta": (code in in_sta) if sta_known else None,
                "rinex_days": len(r),
                "processed_days": len(d),
                "waiting_days": len(waiting),
                "waiting_first": waiting[:8],
                "span_years": span,
                "velocity": None if span is None else span >= MIN_SPAN_YEARS,
            }
        )
    # In the series: a fixed solution in some year of the campaign, so a span.
    in_series = [r for r in rows if r["span_years"] is not None]
    return {
        "campaign": c.name,
        "year": year,
        "rinex_dir": str(rnx),
        "sta": sta_name,
        "min_span_years": MIN_SPAN_YEARS,
        "not_connected": NOT_CONNECTED,
        "totals": {
            "rinex_station_days": sum(len(v) for v in rinex.values()),
            "rinex_stations": len(rinex),
            "processed_station_days": sum(len(v) for v in done.values()),
            "processed_stations": len(done),
            # RINEX on disk with no final solution that estimated the station.
            "waiting_in_sta": waiting_in_sta,
            # Never processed as the campaign stands: the STA does not list them.
            "waiting_not_in_sta": waiting_not_in_sta,
            "in_time_series": len(in_series),
            "short_for_velocity": sum(1 for r in in_series if r["velocity"] is False),
        },
        "rows": rows,
    }
