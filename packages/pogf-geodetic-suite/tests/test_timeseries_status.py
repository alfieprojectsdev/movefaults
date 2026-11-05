"""Tests for timeseries.status — the read-only station status API.

Everything here is synthetic. A known ENU model (rate, one EQ step, one planted
Up outlier) is converted to ECEF, written as daily CRD files, and read back
through the real file path, so the test covers CRD parsing, the decimal-year
convention, the offsets catalog and the fit together.
"""
from __future__ import annotations

import json

import numpy as np
import pymap3d
import pytest
from click.testing import CliRunner
from pogf_geodetic_suite.timeseries.analysis import OffsetEvent, OffsetType
from pogf_geodetic_suite.timeseries.cli import group
from pogf_geodetic_suite.timeseries.crd_pipeline import (
    crd_directory_to_enu,
    session_to_decimal_year,
)
from pogf_geodetic_suite.timeseries.status import (
    SCHEMA,
    OutlierMode,
    series_status,
    session_date_to_decimal_year,
    station_status,
)

# ---------------------------------------------------------------------------
# The synthetic truth
# ---------------------------------------------------------------------------

REF, STA = "REF0", "SYN1"
REF_GEO = (14.5, 121.0, 50.0)                  # lat, lon, h: a made-up site
STA_OFFSET_M = np.array([15000.0, 8000.0, 20.0])   # station ENU from REF, m

RATE_MM_YR = np.array([30.0, -12.0, 2.0])      # E, N, U
STEP_MM = np.array([25.0, -10.0, -8.0])        # applied at t >= STEP_T
STEP_T = 2022 + 1 / 365.25                     # 2022 DOY 001, catalog convention
NOISE_MM = np.array([1.5, 1.5, 4.0])
OUTLIER_T = 2021 + 100 / 365.25                # 2021 DOY 100, first segment
OUTLIER_UP_MM = 60.0

T0 = 2020.0


def _small(t: np.ndarray, ve_m_yr: float = 0.03) -> np.ndarray:
    """A simple series in metres with mm-level noise on every component."""
    rng = np.random.default_rng(7)
    enu = np.column_stack([(t - T0) * ve_m_yr, 0 * t, 0 * t])
    return enu + rng.normal(0.0, 0.001, enu.shape)


def _sessions() -> list[tuple[int, int]]:
    return [(y, d) for y in range(2020, 2024) for d in range(1, 366, 3)]


def _truth_enu_mm(t: np.ndarray) -> np.ndarray:
    rng = np.random.default_rng(20261104)
    enu = np.outer(t - T0, RATE_MM_YR)
    enu += np.where((t >= STEP_T)[:, None], STEP_MM, 0.0)
    enu += rng.normal(0.0, NOISE_MM, enu.shape)
    # Exact match: np.isclose's default rtol is +/-0.02 yr at t ~ 2021, five epochs.
    hit = np.abs(t - OUTLIER_T) < 1e-9
    assert hit.sum() == 1
    enu[hit, 2] += OUTLIER_UP_MM
    return enu


def _crd_line(i: int, name: str, xyz: tuple[float, float, float]) -> str:
    x, y, z = xyz
    return f"  {i:3d}  {name} 00000S000  {x:>15.5f} {y:>15.5f}  {z:>15.5f}    A   G"


def _write_crd(path, rows: list[str]) -> None:
    header = (
        "SYNTHETIC TEST NETWORK                                          04-NOV-26 00:00\n"
        "--------------------------------------------------------------------------------\n"
        "LOCAL GEODETIC DATUM: IGS20                 EPOCH: 2020-01-01 00:00:00\n"
        "\n"
        " NUM  STATION NAME           X (M)          Y (M)          Z (M)     FLAG     SYSTEM\n"
        "\n"
    )
    path.write_text(header + "\n".join(rows) + "\n", encoding="ascii")


@pytest.fixture(scope="module")
def campaign(tmp_path_factory):
    """Daily CRD files plus an offsets catalog. Returns (crd_dir, catalog, t)."""
    root = tmp_path_factory.mktemp("status")
    crd_dir = root / "SOL"
    crd_dir.mkdir()
    sessions = _sessions()
    t = np.array([y + d / 365.25 for y, d in sessions])
    enu_mm = _truth_enu_mm(t)
    ref_xyz = pymap3d.geodetic2ecef(*REF_GEO)
    for (y, d), enu in zip(sessions, enu_mm, strict=True):
        e, n, u = STA_OFFSET_M + enu / 1000.0
        sta_xyz = pymap3d.enu2ecef(e, n, u, *REF_GEO)
        _write_crd(
            crd_dir / f"F1_{y % 100:02d}{d:03d}.CRD",
            [_crd_line(1, REF, ref_xyz), _crd_line(2, STA, sta_xyz)],
        )
    catalog = root / "offsets"
    catalog.write_text(
        f"# synthetic\n{STA}  {STEP_T:.4f}  EQ\nOTHR  2021.5000  CE\n", encoding="utf-8"
    )
    return crd_dir, catalog, t


@pytest.fixture(scope="module")
def recorded(campaign):
    crd_dir, catalog, _ = campaign
    return station_status(crd_dir, STA, REF, offsets_catalog=catalog)


@pytest.fixture(scope="module")
def excluded(campaign):
    crd_dir, catalog, _ = campaign
    return station_status(crd_dir, STA, REF, offsets_catalog=catalog,
                          outlier_mode="exclude")


# ---------------------------------------------------------------------------
# The four required properties
# ---------------------------------------------------------------------------


def test_rate_is_recovered_within_tolerance(recorded):
    v = recorded["velocity"]
    got = np.array([v["velocity_mm_yr"][c] for c in "enu"])
    sig = np.array([v["sigma_mm_yr"][c] for c in "enu"])
    # Two years of 3-day sampling: formal sigma ~0.2 mm/yr horizontal.
    assert np.all(np.abs(got - RATE_MM_YR) < np.maximum(4 * sig, 0.3)), (got, sig)
    assert np.all(sig > 0)
    assert v["short_span"] is False
    assert v["covers_latest_epoch"] is True


def test_step_is_placed_at_the_catalog_epoch(recorded):
    segs = recorded["segments"]
    assert len(segs) == 2
    assert segs[0]["t_end"] < STEP_T <= segs[1]["t_start"]
    assert segs[1]["t_start"] == pytest.approx(STEP_T)
    (event,) = recorded["offsets"]          # OTHR's event is not this station's
    assert event == {"t": pytest.approx(STEP_T, abs=1e-4), "type": "EQ",
                     "label": "earthquake", "within_span": True}
    # The jump between the two fitted lines at the step epoch is the step.
    before = segs[0]["line"]
    after = segs[1]["line"]
    for c, true_step in zip("enu", STEP_MM, strict=True):
        slope0 = segs[0]["velocity_mm_yr"][c]
        at_step_before = before[f"{c}_mm"][1] + slope0 * (STEP_T - before["t"][1])
        jump = after[f"{c}_mm"][0] - at_step_before
        assert jump == pytest.approx(true_step, abs=2.0 if c != "u" else 5.0)


def test_planted_outlier_is_flagged(recorded):
    s = recorded["series"]
    flagged = [t for t, f in zip(s["t"], s["outlier"], strict=True) if f]
    assert flagged == [pytest.approx(OUTLIER_T)]
    assert recorded["segments"][0]["n_outliers"] == 1
    assert recorded["segments"][1]["n_outliers"] == 0


def test_nothing_is_dropped_by_default(recorded, campaign):
    _, _, t = campaign
    s = recorded["series"]
    assert recorded["outlier_rule"]["mode"] == "record"
    assert len(s["t"]) == len(t)                 # every file's epoch is returned
    assert all(s["in_fit"])                      # including the flagged one
    for seg in recorded["segments"]:
        assert seg["n_fit"] == seg["n_epochs"]
    assert sum(seg["n_epochs"] for seg in recorded["segments"]) == len(t)


# ---------------------------------------------------------------------------
# The other mode, and the result shape
# ---------------------------------------------------------------------------


def test_exclude_mode_drops_from_fit_but_not_from_series(recorded, excluded):
    s = excluded["series"]
    assert excluded["outlier_rule"]["mode"] == "exclude"
    assert len(s["t"]) == len(recorded["series"]["t"])
    i = s["outlier"].index(True)
    assert s["in_fit"][i] is False
    assert sum(s["in_fit"]) == len(s["t"]) - 1
    seg0 = excluded["segments"][0]
    assert seg0["n_fit"] == seg0["n_epochs"] - 1
    # The outlier sits ABOVE the line and AFTER segment 0's mid-point, so
    # keeping it can only tilt that segment's Up slope upward. (Not "closer to
    # the truth": a 0.2 mm/yr pull is below this noise's own slope error.)
    up_rec = recorded["segments"][0]["velocity_mm_yr"]["u"]
    up_exc = seg0["velocity_mm_yr"]["u"]
    assert up_rec - up_exc > 0.05
    # The final segment holds no outlier, so the published velocity is the same.
    assert excluded["velocity"] == recorded["velocity"]


def test_default_mode_is_record():
    t = np.linspace(2020, 2022, 50)
    out = series_status(t, _small(t), station="X")
    assert out["outlier_rule"]["mode"] == OutlierMode.RECORD.value == "record"


def test_result_is_strict_json_and_round_trips(recorded):
    text = json.dumps(recorded, allow_nan=False)
    assert json.loads(text) == recorded
    assert recorded["schema"] == SCHEMA
    assert recorded["reference"] == REF
    assert len(recorded["offsets_catalog"]["sha256"]) == 64
    n = len(recorded["series"]["t"])
    for key in ("e_mm", "n_mm", "u_mm", "outlier", "in_fit", "segment"):
        assert len(recorded["series"][key]) == n


def test_series_is_relative_to_origin_and_lossless(recorded, campaign):
    s = recorded["series"]
    assert (s["e_mm"][0], s["n_mm"][0], s["u_mm"][0]) == (0.0, 0.0, 0.0)
    # origin + relative recovers the absolute ENU: about 15 km E of REF.
    assert recorded["origin_m"]["e"] == pytest.approx(STA_OFFSET_M[0], abs=0.05)
    assert recorded["origin_m"]["n"] == pytest.approx(STA_OFFSET_M[1], abs=0.05)


@pytest.mark.parametrize("mode", ["recorded", "excluded"])
def test_fit_matches_an_independent_fit(mode, request):
    """Slope and line agree with np.polyfit over exactly the in_fit epochs."""
    result = request.getfixturevalue(mode)
    s = result["series"]
    t = np.array(s["t"])
    for k, seg in enumerate(result["segments"]):
        sel = np.array([g == k for g in s["segment"]]) & np.array(s["in_fit"])
        for c in "enu":
            slope, icpt = np.polyfit(t[sel], np.array(s[f"{c}_mm"])[sel], 1)
            assert seg["velocity_mm_yr"][c] == pytest.approx(slope, abs=1e-6)
            want = icpt + slope * np.array(seg["line"]["t"])
            assert seg["line"][f"{c}_mm"] == pytest.approx(want, abs=1e-6)


# ---------------------------------------------------------------------------
# Warnings: what the data cannot support is said, not hidden
# ---------------------------------------------------------------------------


def test_without_a_catalog_one_segment_and_a_warning(campaign):
    crd_dir, _, _ = campaign
    out = station_status(crd_dir, STA, REF)
    assert out["offsets_catalog"] is None
    assert len(out["segments"]) == 1
    assert any("no offsets supplied" in w for w in out["warnings"])


def test_catalog_present_but_no_events_for_station(campaign, tmp_path):
    crd_dir, _, _ = campaign
    cat = tmp_path / "offsets"
    cat.write_text("OTHR  2021.5000  CE\n", encoding="utf-8")
    out = station_status(crd_dir, STA, REF, offsets_catalog=cat)
    assert out["offsets"] == []
    assert any("no offset events for this station" in w for w in out["warnings"])


def test_catalog_case_variants_are_merged_not_overwritten(campaign, tmp_path):
    crd_dir, _, _ = campaign
    cat = tmp_path / "offsets"
    cat.write_text(
        f"{STA.upper()}  2021.0000  CE\n{STA.lower()}  2022.0000  EQ\n",
        encoding="utf-8",
    )
    out = station_status(crd_dir, STA, REF, offsets_catalog=cat)
    assert [o["t"] for o in out["offsets"]] == [2021.0, 2022.0]


def test_short_final_segment_is_flagged_not_hidden():
    t = 2020 + np.arange(0, 400) / 365.25 * 3          # ~3.3 years
    enu = _small(t)
    late = OffsetEvent(date=float(t[-40]), offset_type=OffsetType.CE)  # ~0.3 yr
    out = series_status(t, enu, station="X", offsets=[late])
    assert out["velocity"]["short_span"] is True
    assert out["velocity"]["covers_latest_epoch"] is True
    assert any("not a secular rate" in w for w in out["warnings"])


def test_unfittable_last_interval_says_velocity_is_pre_event():
    """estimate_velocity skips a <3-epoch interval silently; we must not."""
    t = 2020 + np.arange(0, 200) / 365.25 * 3
    enu = _small(t)
    late = OffsetEvent(date=float(t[-2]), offset_type=OffsetType.EQ)  # 2 epochs after
    out = series_status(t, enu, station="X", offsets=[late])
    assert out["velocity"]["covers_latest_epoch"] is False
    assert out["series"]["segment"][-2:] == [None, None]
    assert out["series"]["in_fit"][-2:] == [False, False]
    assert any("BEFORE that offset" in w for w in out["warnings"])
    assert len(out["series"]["t"]) == 200                # still returned


def test_duplicate_epochs_are_warned():
    t = np.repeat(np.linspace(2020, 2022, 30), 2)
    enu = _small(t)
    out = series_status(t, enu, station="X", offsets=[])
    assert any("duplicate epoch" in w for w in out["warnings"])


def test_duplicate_day_flags_only_the_outlying_copy():
    """Two files for one day, one bad: only that copy is flagged or dropped."""
    t = np.linspace(2020, 2022, 60)
    enu = _small(t)
    t = np.append(t, t[30])
    enu = np.vstack([enu, enu[30]])
    enu[30, 2] += 0.5                                     # one copy is an outlier
    out = series_status(t, enu, station="X", offsets=[], outlier_mode="exclude")
    seg = out["segments"][0]
    assert sum(out["series"]["outlier"]) == seg["n_outliers"] == 1
    assert sum(out["series"]["in_fit"]) == seg["n_fit"] == 60


def test_flags_come_from_the_fit_not_a_second_copy_of_the_rule(monkeypatch):
    """Change the fit's rule and the status flags follow it.

    status.py used to re-run `_detect_outliers_iqr` itself. Swap in a rule the
    IQR test would never produce (flag the first row of every segment) and the
    status flags must still match the fit's, in both modes.
    """
    from pogf_geodetic_suite.timeseries import analysis

    def first_row_only(data, factor):
        mask = np.zeros(len(data), dtype=bool)
        mask[0] = True
        return mask

    monkeypatch.setattr(analysis, "_detect_outliers_iqr", first_row_only)
    t = np.linspace(2020, 2022, 40)
    for mode in ("record", "exclude"):
        out = series_status(t, _small(t), station="X", offsets=[], outlier_mode=mode)
        s = out["series"]
        assert [i for i, f in enumerate(s["outlier"]) if f] == [0]
        assert out["segments"][0]["n_outliers"] == 1
        assert s["in_fit"][0] is (mode == "record")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def test_station_equal_to_reference_is_refused(campaign):
    crd_dir, _, _ = campaign
    with pytest.raises(ValueError, match="reference station"):
        station_status(crd_dir, REF, REF)


def test_unknown_station_is_refused(campaign):
    crd_dir, _, _ = campaign
    with pytest.raises(ValueError, match="NOPE"):
        station_status(crd_dir, "NOPE", REF)


def test_nan_is_refused_before_it_reaches_json():
    t = np.linspace(2020, 2022, 30)
    enu = np.zeros((30, 3))
    enu[5, 1] = np.nan
    with pytest.raises(ValueError, match="NaN"):
        series_status(t, enu, station="X")


def test_unknown_outlier_mode_is_refused():
    t = np.linspace(2020, 2022, 30)
    with pytest.raises(ValueError):
        series_status(t, np.zeros((30, 3)), station="X", outlier_mode="drop")


@pytest.mark.parametrize("factor", [float("nan"), float("inf"), 0.0, -1.0])
def test_unusable_iqr_factor_is_refused(factor):
    # NaN/inf would be echoed into outlier_rule and break allow_nan=False;
    # a factor <= 0 flags nearly every epoch.
    t = np.linspace(2020, 2022, 30)
    with pytest.raises(ValueError, match="outlier_iqr_factor"):
        series_status(t, np.zeros((30, 3)), station="X", outlier_iqr_factor=factor)


def test_zero_span_segment_is_warned():
    t = np.full(5, 2020.0)
    enu = np.random.default_rng(0).normal(size=(5, 3)) * 1e-3
    out = series_status(t, enu, station="X")
    assert any("one time" in w for w in out["warnings"])


def test_leading_unfittable_interval_is_not_called_between():
    t = np.linspace(2020, 2022, 30)
    offsets = [OffsetEvent(date=float(t[2]), offset_type=OffsetType.EQ)]
    out = series_status(t, np.zeros((30, 3)), station="X", offsets=offsets)
    assert out["series"]["segment"][:2] == [None, None]
    assert any("before or between" in w for w in out["warnings"])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_status_prints_the_same_json(campaign, recorded):
    crd_dir, catalog, _ = campaign
    res = CliRunner().invoke(
        group, ["status", str(crd_dir), "-s", STA, "-r", REF, "--offsets", str(catalog)]
    )
    assert res.exit_code == 0, res.output
    assert json.loads(res.output) == recorded


def test_cli_status_error_exits_nonzero(campaign):
    crd_dir, _, _ = campaign
    res = CliRunner().invoke(group, ["status", str(crd_dir), "-s", "NOPE", "-r", REF])
    assert res.exit_code == 1
    assert "NOPE" in res.output


def test_cli_group_keeps_plots_command():
    res = CliRunner().invoke(group, ["plots", "--help"])
    assert res.exit_code == 0
    assert "PLOT" in res.output


# ---------------------------------------------------------------------------
# exclude_sessions: epochs a person confirmed as outliers
# ---------------------------------------------------------------------------


def test_no_exclusions_is_the_published_fit(recorded, campaign):
    crd_dir, catalog, _ = campaign
    again = station_status(crd_dir, STA, REF, offsets_catalog=catalog, exclude_sessions=[])
    assert again == recorded
    assert recorded["exclusions"] == {"requested": 0, "matched": 0, "unmatched": []}
    assert not any(recorded["series"]["excluded"])


def test_an_excluded_session_leaves_the_fit_and_keeps_its_flag(recorded, campaign):
    crd_dir, catalog, _ = campaign
    out = station_status(
        crd_dir, STA, REF, offsets_catalog=catalog, exclude_sessions=["2021-100", "2030-001"]
    )
    s = out["series"]
    i = s["t"].index(OUTLIER_T)
    assert s["excluded"][i] is True and s["in_fit"][i] is False
    assert s["outlier"] == recorded["series"]["outlier"], "the rule's flags are unchanged"
    assert out["outlier_rule"]["mode"] == "record"
    assert out["exclusions"]["requested"] == 2 and out["exclusions"]["matched"] == 1
    assert len(out["exclusions"]["unmatched"]) == 1
    seg0 = out["segments"][0]
    assert seg0["n_fit"] == recorded["segments"][0]["n_fit"] - 1
    assert seg0["velocity_mm_yr"]["u"] != recorded["segments"][0]["velocity_mm_yr"]["u"]
    json.dumps(out, allow_nan=False)


def test_session_dates_are_checked(campaign):
    crd_dir, catalog, _ = campaign
    for bad in ("2021-1", "21100", "1970-001", "2021-000", "2021-367", "2081-001"):
        with pytest.raises(ValueError):
            station_status(crd_dir, STA, REF, offsets_catalog=catalog, exclude_sessions=[bad])


@pytest.mark.parametrize(
    ("session_date", "filenames"),
    [
        ("2025-218", ("FIN_20252180.CRD", "F1_25218.CRD")),
        ("2024-366", ("FIN_20243660.CRD", "F1_24366.CRD")),
        ("1999-001", ("FIN_19990010.CRD", "F1_99001.CRD")),
        ("2080-365", ("FIN_20803650.CRD", "F1_80365.CRD")),
    ],
)
def test_session_date_is_bit_for_bit_the_crd_files_epoch(session_date, filenames):
    """The exclusion matches series.t exactly only if it is the very float
    crd_directory_to_enu gives that day's file, in both naming forms."""
    from pogf_geodetic_suite.timeseries.crd_pipeline import (
        _extract_session_from_filename,
        session_to_decimal_year,
    )

    want = session_date_to_decimal_year(session_date)
    for name in filenames:
        assert session_to_decimal_year(_extract_session_from_filename(name)) == want


def test_duplicate_requests_are_counted_once(campaign):
    crd_dir, catalog, _ = campaign
    out = station_status(
        crd_dir, STA, REF, offsets_catalog=catalog,
        exclude_sessions=["2021-100", "2021-100", "2030-001", "2030-001"],
    )  # fmt: skip
    assert out["exclusions"]["requested"] == 2
    assert out["exclusions"]["matched"] == 1
    assert len(out["exclusions"]["unmatched"]) == 1
    assert sum(out["series"]["excluded"]) == 1


# --- a series spanning years: several directories read as one ------------------------------


def _year_dirs(tmp_path, datums=("IGS20", "IGS20")):
    """REF0 still, SYN1 moving 10 mm/yr east, one folder per year."""
    ref = (-3186000.0, 5345000.0, 1640000.0)
    dirs = []
    for year, datum in zip((2024, 2025), datums, strict=True):
        d = tmp_path / str(year) / "STA"
        d.mkdir(parents=True)
        for doy in range(1, 361, 30):
            t = year + doy / 365.25
            dx = 0.010 * (t - 2024)
            lines = [
                "SYNTHETIC",
                "-" * 40,
                f"LOCAL GEODETIC DATUM: {datum}             EPOCH: {year}-01-01 12:00:00",
                "",
                " NUM  STATION NAME           X (M)          Y (M)          Z (M)     FLAG     SYSTEM",
                "",
                f"  1  REF0 00000S000  {ref[0]:>15.5f} {ref[1]:>15.5f}  {ref[2]:>15.5f}    A   G",
                f"  2  SYN1 00000S000  {ref[0] + 900 + dx:>15.5f} {ref[1] + 500:>15.5f}  {ref[2] + 300:>15.5f}    A   G",
            ]
            (d / f"F1_{year % 100:02d}{doy:03d}.CRD").write_text("\n".join(lines) + "\n")
        dirs.append(d)
    return dirs


def test_several_directories_are_one_series(tmp_path) -> None:
    dirs = _year_dirs(tmp_path)
    whole = station_status(dirs, "SYN1", "REF0")
    first = station_status(dirs[0], "SYN1", "REF0")
    t = whole["series"]["t"]
    assert t == sorted(t) and int(t[0]) == 2024 and int(t[-1]) == 2025
    n = len(first["series"]["t"])
    # The first year's values are the same as read alone.
    assert whole["series"]["e_mm"][:n] == pytest.approx(first["series"]["e_mm"])
    assert whole["velocity"]["span_yr"] > 1.5 and not whole["velocity"]["short_span"]
    # The slope spans the join: no jump between one year's folder and the next.
    gaps = np.abs(np.diff(whole["series"]["e_mm"]))
    assert gaps.max() < 3 * np.median(gaps)


def test_one_directory_still_reads_as_it_did(tmp_path) -> None:
    d = _year_dirs(tmp_path)[0]
    assert station_status(d, "SYN1", "REF0") == station_status([d], "SYN1", "REF0")
    assert station_status(str(d), "SYN1", "REF0")["series"]["t"]


def test_files_in_two_datums_are_warned_about(tmp_path) -> None:
    same = station_status(_year_dirs(tmp_path / "a"), "SYN1", "REF0")
    assert not [w for w in same["warnings"] if "datum" in w]
    mixed = station_status(_year_dirs(tmp_path / "b", ("IGS14", "IGS20")), "SYN1", "REF0")
    (w,) = [w for w in mixed["warnings"] if "datum" in w]
    assert w.index("IGS14") < w.index("IGS20") and "not motion" in w


def test_a_datum_the_station_has_no_epoch_in_is_not_warned_about(tmp_path) -> None:
    dirs = _year_dirs(tmp_path, ("IGS14", "IGS20"))
    for f in dirs[0].glob("*.CRD"):
        f.write_text("".join(ln for ln in f.read_text().splitlines(True) if "SYN1" not in ln))
    out = station_status(dirs, "SYN1", "REF0")
    assert not [w for w in out["warnings"] if "datum" in w]


def test_days_the_reference_is_absent_are_named_in_the_warnings(tmp_path) -> None:
    dirs = _year_dirs(tmp_path)
    assert not [w for w in station_status(dirs, "SYN1", "REF0")["warnings"] if "missing" in w]
    for f in dirs[0].glob("*.CRD"):  # a whole year without the reference
        f.write_text("".join(ln for ln in f.read_text().splitlines(True) if "REF0" not in ln))
    out = station_status(dirs, "SYN1", "REF0")
    (w,) = [w for w in out["warnings"] if "missing" in w]
    assert "REF0" in w and "12 of 24" in w
    assert int(out["series"]["t"][0]) == 2025


def test_a_message_names_several_directories_as_paths(tmp_path) -> None:
    dirs = _year_dirs(tmp_path)
    with pytest.raises(ValueError) as exc:
        station_status(dirs, "NOPE", "REF0")
    assert "PosixPath" not in str(exc.value) and str(dirs[1]) in str(exc.value)


def test_one_station_is_the_whole_result_filtered(tmp_path) -> None:
    dirs = _year_dirs(tmp_path)
    assert crd_directory_to_enu(dirs, "REF0", station="syn1") == [
        ep for ep in crd_directory_to_enu(dirs, "REF0") if ep.station == "SYN1"
    ]


def test_a_crd_is_parsed_once_until_it_changes(tmp_path, monkeypatch) -> None:
    from pogf_geodetic_suite.timeseries import crd_pipeline

    dirs = _year_dirs(tmp_path)
    real = crd_pipeline.read_crd_file
    calls: list[str] = []
    monkeypatch.setattr(
        crd_pipeline, "read_crd_file", lambda p: (calls.append(p.name), real(p))[1]
    )
    first = station_status(dirs, "SYN1", "REF0")
    n = len(calls)
    assert n == len(first["series"]["t"])
    assert station_status(dirs, "SYN1", "REF0") == first
    assert len(calls) == n, "nothing changed, nothing reparsed"
    changed = dirs[0] / "F1_24001.CRD"
    changed.write_text(changed.read_text().replace("-3186000.00000", "-3186001.00000"))
    again = station_status(dirs, "SYN1", "REF0")
    assert calls[n:] == ["F1_24001.CRD"], "only the changed file"
    assert again != first


_REF_XYZ = (-3186000.0, 5345000.0, 1640000.0)
_RATE_Y_MM_YR = 30.0


def _pair(tmp_path, offset_m: float):
    """A still reference, and a station `offset_m` away along the Y axis moving
    along that axis at `_RATE_Y_MM_YR`."""
    x, y, z = _REF_XYZ
    for doy in range(1, 361, 30):
        moved = _RATE_Y_MM_YR / 1000.0 * (session_to_decimal_year(f"24{doy:03d}") - 2024.0)
        lines = [
            "SYNTHETIC", "-" * 40, "LOCAL GEODETIC DATUM: IGS20", "",
            " NUM  STATION NAME           X (M)          Y (M)          Z (M)     FLAG     SYSTEM", "",
            f"  1  REF0 00000S000  {x:>15.5f} {y:>15.5f}  {z:>15.5f}    A   G",
            f"  2  SYN1 00000S000  {x:>15.5f} {y + offset_m + moved:>15.5f}  {z:>15.5f}    A   G",
        ]  # fmt: skip
        (tmp_path / f"F1_24{doy:03d}.CRD").write_text("\n".join(lines) + "\n")
    return tmp_path


def _rate_in_axes_at(x: float, y: float, z: float) -> tuple[float, float, float]:
    """The station's Y motion, in mm/yr, in the local axes at that position."""
    lat, lon, _ = pymap3d.ecef2geodetic(x, y, z, deg=True)
    return pymap3d.ecef2enuv(0.0, _RATE_Y_MM_YR, 0.0, lat, lon, deg=True)


def test_a_near_reference_gives_its_distance_and_no_warning(tmp_path) -> None:
    r = station_status(_pair(tmp_path, 100_000.0), "SYN1", "REF0")
    assert r["reference_distance_deg"] == pytest.approx(0.9, abs=0.01)
    assert r["reference_warning"] is None
    assert not [w for w in r["warnings"] if "degrees" in w]


def test_a_far_reference_is_warned_about_and_the_numbers_do_not_change(tmp_path) -> None:
    offset = 1_000_000.0
    r = station_status(_pair(tmp_path, offset), "SYN1", "REF0")
    assert r["reference_distance_deg"] == pytest.approx(9.0, abs=0.01)
    assert "9.0 degrees from SYN1" in r["reference_warning"]
    assert r["reference_warning"] in r["warnings"], "the one sentence, in both places"
    # Still the reference's axes, worked out here independently of the pipeline.
    # Their own-axes counterpart differs by millimetres, so warning instead of
    # correcting is what this holds: a rotation to the station's axes turns it red.
    v = r["velocity"]["velocity_mm_yr"]
    refs_axes = _rate_in_axes_at(*_REF_XYZ)
    assert (v["e"], v["n"], v["u"]) == pytest.approx(refs_axes, abs=0.01)
    x, y, z = _REF_XYZ
    own_axes = _rate_in_axes_at(x, y + offset, z)
    assert max(abs(a - b) for a, b in zip(refs_axes, own_axes, strict=True)) > 1.0
