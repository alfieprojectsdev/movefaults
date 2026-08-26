"""Tests for the network filter and PLOT writer — steps 00 and 04 of the
legacy chain, the two that were never ported.

The load-bearing tests are:

* `test_network_definitions_match_the_legacy_bat_files` — the YAML has to
  reproduce the three `00_CRD_*.bat` exclusion lists exactly, or the ported
  pipeline silently processes a different station set than production did.
* `test_writing_twice_does_not_double_the_series` — `RUNX_v2.py` appends with
  no truncation, so a second run doubles every series. That failure looks like
  extra data rather than an error.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from pogf_geodetic_suite.timeseries.crd_pipeline import StationEpoch
from pogf_geodetic_suite.timeseries.plots import (
    available_networks,
    crd_directory_to_plots,
    filter_epochs,
    load_network,
    write_plot_files,
)

BAT_DIR = Path(__file__).resolve().parents[3] / "analysis" / "02 Time Series"


def _epoch(station: str, year: float, e=1.0, n=2.0, u=3.0) -> StationEpoch:
    return StationEpoch(station=station, decimal_year=year, east_m=e, north_m=n, up_m=u)


def _write_crd(path: Path, stations: list[dict]) -> None:
    header = (
        "PHIVOLCS CORS NETWORK                                           01-MAY-26 00:00\n"
        "--------------------------------------------------------------------------------\n"
        "LOCAL GEODETIC DATUM: IGS14                 EPOCH: 2015-01-01 00:00:00\n"
        "\n"
        " NUM  STATION NAME           X (M)          Y (M)          Z (M)     FLAG     SYSTEM\n"
        "\n"
    )
    rows = []
    for i, s in enumerate(stations, start=1):
        sname = f"{s['name'][:4]} 00000S000"
        rows.append(
            f"  {i:3d}  {sname:<14}  {s['x']:>15.5f} {s['y']:>15.5f}  {s['z']:>15.5f}    IGS14"
        )
    path.write_text(header + "\n".join(rows) + "\n", encoding="ascii")


# ---------------------------------------------------------------------------
# the network definitions must match the .bat files they replace
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["NP", "NAMRIA", "PIVS"])
def test_network_definitions_match_the_legacy_bat_files(name):
    """Config parity with `00_CRD_<name>.bat`.

    The .bat content is one `findstr /V "<~270 codes>"`. If the YAML and the
    .bat disagree the ported pipeline processes a different network than
    production did, and nothing downstream would notice.
    """
    bat = BAT_DIR / f"00_CRD_{name}.bat"
    if not bat.exists():
        pytest.skip(f"{bat} not present")
    m = re.search(r'findstr /V "([^"]*)"', bat.read_text(errors="replace"))
    assert m, "could not find the findstr exclusion list"
    legacy = {c.upper() for c in m.group(1).split()}
    assert load_network(name).exclusions == legacy


def test_available_networks():
    assert set(available_networks()) == {"NP", "NAMRIA", "PIVS"}


def test_load_network_is_case_insensitive():
    assert load_network("pivs").name == load_network("PIVS").name


def test_unknown_network_names_the_ones_that_exist():
    # A typo here silently processes the wrong station set, so the error has to
    # be loud and has to say what the alternatives are.
    with pytest.raises(KeyError, match="NAMRIA"):
        load_network("PIVSS")


def test_np_is_the_widest_network():
    """NP excludes only the common IGS set; the other two subtract further."""
    np_, namria, pivs = (load_network(n) for n in ("NP", "NAMRIA", "PIVS"))
    assert np_.exclusions < namria.exclusions
    assert np_.exclusions < pivs.exclusions


def test_namria_and_pivs_differ_in_which_stations_they_drop():
    """The only real difference between the three .bat files.

    NAMRIA drops the far-field IGS stations and keeps the regional ties; PIVS
    does the reverse. That distinction was invisible in the .bat files.
    """
    namria = load_network("NAMRIA").exclusions
    pivs = load_network("PIVS").exclusions
    assert {"TWTF", "USUD", "SHAO"} <= namria      # far-field, dropped by NAMRIA
    assert {"TWTF", "USUD", "SHAO"}.isdisjoint(pivs)
    assert {"AIRA", "DARW", "PNGM"} <= pivs        # regional, dropped by PIVS
    assert {"AIRA", "DARW", "PNGM"}.isdisjoint(namria)


# ---------------------------------------------------------------------------
# filtering
# ---------------------------------------------------------------------------


def test_filter_epochs_drops_excluded_stations():
    net = load_network("PIVS")
    epochs = [_epoch("ALCO", 2025.1), _epoch("AIRA", 2025.1), _epoch("MAR2", 2025.1)]
    kept = {e.station for e in filter_epochs(epochs, net)}
    assert kept == {"ALCO", "MAR2"}


def test_filter_is_case_insensitive_on_station_code():
    net = load_network("PIVS")
    assert filter_epochs([_epoch("aira", 2025.1)], net) == []


# ---------------------------------------------------------------------------
# PLOT writing
# ---------------------------------------------------------------------------


def test_write_plot_files_one_file_per_station(tmp_path):
    written = write_plot_files(
        [_epoch("ALCO", 2025.1), _epoch("ALCO", 2025.2), _epoch("MAR2", 2025.1)], tmp_path
    )
    assert set(written) == {"ALCO", "MAR2"}
    assert (tmp_path / "ALCO").exists()
    assert len((tmp_path / "ALCO").read_text().strip().splitlines()) == 2


def test_plot_line_format_matches_what_downstream_parses(tmp_path):
    """`decimal_year  E  N  U`, four decimals — the reviewer and
    compare_velocity_outlier_policy.py both parse this."""
    write_plot_files([_epoch("ALCO", 2025.7474, 1.5, -2.25, 0.125)], tmp_path)
    line = (tmp_path / "ALCO").read_text().strip()
    fields = line.split()
    assert len(fields) == 4
    assert fields[0] == "2025.7474"
    assert [float(f) for f in fields[1:]] == [1.5, -2.25, 0.125]


def test_epochs_are_written_in_time_order(tmp_path):
    write_plot_files(
        [_epoch("ALCO", 2025.9), _epoch("ALCO", 2025.1), _epoch("ALCO", 2025.5)], tmp_path
    )
    years = [float(ln.split()[0]) for ln in (tmp_path / "ALCO").read_text().splitlines()]
    assert years == sorted(years)


def test_writing_twice_does_not_double_the_series(tmp_path):
    """RUNX_v2.py appends with no truncation; running it twice doubles every
    series, which looks like extra data rather than an error."""
    epochs = [_epoch("ALCO", 2025.1), _epoch("ALCO", 2025.2)]
    write_plot_files(epochs, tmp_path)
    write_plot_files(epochs, tmp_path)
    assert len((tmp_path / "ALCO").read_text().strip().splitlines()) == 2


def test_site_list_file_is_written(tmp_path):
    write_plot_files([_epoch("MAR2", 2025.1), _epoch("ALCO", 2025.1)], tmp_path)
    assert (tmp_path / "123").read_text().split() == ["ALCO", "MAR2"]


def test_site_list_can_be_suppressed(tmp_path):
    write_plot_files([_epoch("ALCO", 2025.1)], tmp_path, write_site_list=False)
    assert not (tmp_path / "123").exists()


# ---------------------------------------------------------------------------
# end to end: 00 -> 04
# ---------------------------------------------------------------------------


def test_crd_directory_to_plots_end_to_end(tmp_path):
    crd_dir = tmp_path / "SOL"
    crd_dir.mkdir()
    stations = [
        {"name": "PIMO", "x": -3186597.0, "y": 5344958.0, "z": 1567918.0},
        {"name": "ALCO", "x": -3186000.0, "y": 5345000.0, "z": 1568000.0},
        {"name": "AIRA", "x": -3530000.0, "y": 4118000.0, "z": 3344000.0},
    ]
    _write_crd(crd_dir / "F1_25001.CRD", stations)
    _write_crd(crd_dir / "F1_25002.CRD", stations)

    out = tmp_path / "PLOTS"
    written = crd_directory_to_plots(crd_dir, out, "PIMO", "PIVS")

    # PIMO is the reference (dropped by the ENU step); AIRA is excluded by PIVS
    assert set(written) == {"ALCO"}
    assert len((out / "ALCO").read_text().strip().splitlines()) == 2


def test_end_to_end_raises_when_the_network_excludes_everything(tmp_path):
    crd_dir = tmp_path / "SOL"
    crd_dir.mkdir()
    _write_crd(
        crd_dir / "F1_25001.CRD",
        [
            {"name": "PIMO", "x": -3186597.0, "y": 5344958.0, "z": 1567918.0},
            {"name": "AIRA", "x": -3530000.0, "y": 4118000.0, "z": 3344000.0},
        ],
    )
    with pytest.raises(ValueError, match="excluded every station"):
        crd_directory_to_plots(crd_dir, tmp_path / "PLOTS", "PIMO", "PIVS")
