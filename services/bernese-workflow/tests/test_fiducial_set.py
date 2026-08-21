"""Tests for fiducial-set resolution and recording (GEO-001)."""
import hashlib
from pathlib import Path

import pytest
from bernese_workflow.fiducial_set import (
    FiducialSetError,
    extract_freesta_reference,
    load_fiducial_set,
    parse_fix_file,
    resolve_panel_path,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_PANELS = REPO_ROOT / "config" / "bernese" / "gpsuser52-luzon" / "OPT"

# Representative Bernese station-selection file: title, underline, then the six
# fiducials the Luzon final solution uses as its minimum constraint.
SAMPLE_FIX = """\
Station selection file                                   21-AUG-26 12:00
--------------------------------------------------------------------------------

STATION NAME
****************
ALIC 50137M001
DAEJ 23902M002
DARW 50134M001
MCIL 21768S001
PIMO 22003M001
PNGM 50201M001
"""

PANEL_FROM_FILE = (
    'FREESTA 1  "FROM_FILE"\n'
    'FREESTA_F 1  "${P}/PHIVOLCS\\STA\\REF190110.FIX"\n'
)


def _panel(tmp_path: Path, body: str, name: str = "ADDNEQ2.INP") -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def _fix(tmp_path: Path, body: str = SAMPLE_FIX) -> Path:
    d = tmp_path / "PHIVOLCS" / "STA"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "REF190110.FIX"
    p.write_text(body, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Panel reading
# ---------------------------------------------------------------------------

def test_extract_reads_mode_and_file():
    mode, fix = extract_freesta_reference(PANEL_FROM_FILE)
    assert mode == "FROM_FILE"
    assert fix == "${P}/PHIVOLCS\\STA\\REF190110.FIX"


def test_extract_returns_none_when_absent():
    assert extract_freesta_reference("SOMETHING 1  \"else\"\n") == (None, None)


def test_extract_ignores_related_keys():
    """FREESTA_L / FREESTA_G are different datum modes, not the file."""
    mode, fix = extract_freesta_reference(
        'FREESTA 1  "FROM_FILE"\n'
        'FREESTA_L 0\n'
        'FREESTA_G 0\n'
        'FREESTA_F 1  "${P}/STA/X.FIX"\n'
    )
    assert mode == "FROM_FILE"
    assert fix == "${P}/STA/X.FIX"


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def test_resolve_expands_variable_and_converts_separators():
    got = resolve_panel_path("${P}/PHIVOLCS\\STA\\REF190110.FIX", {"P": "/campaigns"})
    assert got == Path("/campaigns/PHIVOLCS/STA/REF190110.FIX")


def test_resolve_handles_bare_dollar_variable():
    assert resolve_panel_path("$P/STA/X.FIX", {"P": "/c"}) == Path("/c/STA/X.FIX")


def test_resolve_names_the_missing_variable():
    """A literal ${P} left in the path fails later as a confusing ENOENT."""
    with pytest.raises(FiducialSetError, match=r"no value for \$\{P\}"):
        resolve_panel_path("${P}/STA/X.FIX", {})


# ---------------------------------------------------------------------------
# .FIX parsing
# ---------------------------------------------------------------------------

def test_parse_fix_reads_stations_in_order(tmp_path):
    assert parse_fix_file(_fix(tmp_path)) == (
        "ALIC", "DAEJ", "DARW", "MCIL", "PIMO", "PNGM",
    )


def test_parse_fix_skips_header_and_column_titles(tmp_path):
    stations = parse_fix_file(_fix(tmp_path))
    assert "STAT" not in stations
    assert "NAME" not in stations


def test_parse_fix_accepts_bare_codes_without_domes(tmp_path):
    p = _fix(tmp_path, "Station selection\n----\n\nALIC\nPIMO\n")
    assert parse_fix_file(p) == ("ALIC", "PIMO")


def test_parse_fix_raises_on_empty_set(tmp_path):
    """An empty fiducial set is not a datum definition."""
    p = _fix(tmp_path, "Station selection file\n------------\n\n")
    with pytest.raises(FiducialSetError, match="no station entries"):
        parse_fix_file(p)


def test_parse_fix_raises_on_unreadable(tmp_path):
    with pytest.raises(FiducialSetError, match="cannot read fiducial file"):
        parse_fix_file(tmp_path / "nope.FIX")


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------

def test_load_records_hash_and_stations(tmp_path):
    fix = _fix(tmp_path)
    panel = _panel(tmp_path, PANEL_FROM_FILE)

    fs = load_fiducial_set(panel, {"P": str(tmp_path)})

    assert fs is not None
    assert fs.station_count == 6
    assert fs.stations[0] == "ALIC"
    assert fs.sha256 == hashlib.sha256(fix.read_bytes()).hexdigest()
    assert fs.size_bytes == fix.stat().st_size
    assert fs.resolved_path == fix


def test_load_record_is_serialisable(tmp_path):
    _fix(tmp_path)
    panel = _panel(tmp_path, PANEL_FROM_FILE)
    d = load_fiducial_set(panel, {"P": str(tmp_path)}).to_dict()
    assert d["station_count"] == 6
    assert d["stations"][:2] == ["ALIC", "DAEJ"]
    assert len(d["sha256"]) == 64
    # The unexpanded reference is kept: it is what the panel actually says,
    # and it is the thing that turns out to be frozen to 2019 DOY 011.
    assert "REF190110.FIX" in d["raw_reference"]


def test_load_returns_none_for_non_file_datum_modes(tmp_path):
    panel = _panel(tmp_path, 'FREESTA 1  "MANUAL"\nFREESTA_L 1  "PIMO"\n')
    assert load_fiducial_set(panel, {"P": str(tmp_path)}) is None


def test_load_raises_when_file_missing(tmp_path):
    """The failure this module exists to prevent.

    BPE proceeds on a different datum definition when the station-selection
    file is absent, and the resulting coordinates look entirely normal.
    """
    panel = _panel(tmp_path, PANEL_FROM_FILE)   # no .FIX written
    with pytest.raises(FiducialSetError, match="not a readable file"):
        load_fiducial_set(panel, {"P": str(tmp_path)})


def test_load_raises_when_freesta_f_empty(tmp_path):
    panel = _panel(tmp_path, 'FREESTA 1  "FROM_FILE"\nFREESTA_F 1  ""\n')
    with pytest.raises(FiducialSetError, match="FREESTA_F is empty"):
        load_fiducial_set(panel, {"P": str(tmp_path)})


def test_load_raises_on_non_addneq2_panel(tmp_path):
    panel = _panel(tmp_path, 'MAPPNG 1  "WET_GMF"\n')
    with pytest.raises(FiducialSetError, match="no FREESTA key"):
        load_fiducial_set(panel, {"P": str(tmp_path)})


# ---------------------------------------------------------------------------
# The panels actually committed here
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not REAL_PANELS.exists(), reason="panels not present")
def test_committed_panels_all_define_datum_from_file():
    """Every ADDNEQ2 panel in the Luzon config uses FROM_FILE.

    If one ever stops doing so, the datum is defined some other way and this
    module would silently return None for it.
    """
    panels = sorted(REAL_PANELS.glob("*/ADDNEQ2.INP"))
    assert panels, "expected ADDNEQ2 panels under the Luzon OPT tree"
    for panel in panels:
        mode, fix = extract_freesta_reference(
            panel.read_text(encoding="utf-8", errors="replace")
        )
        assert mode == "FROM_FILE", f"{panel.parent.name} uses FREESTA={mode}"
        assert fix, f"{panel.parent.name} has FREESTA=FROM_FILE but no file"


@pytest.mark.skipif(not REAL_PANELS.exists(), reason="panels not present")
def test_committed_panels_reference_a_frozen_fiducial_file():
    """Records the state found on 2026-08-21, so a change is visible.

    Four of the five panels in this tree name REF190110.FIX -- 2019, day 011 --
    and PHI_WK names another campaign's REF192560.FIX. (A sixth ADDNEQ2 panel,
    PGN_WK, lives in the NAMRIA `gpsuser` tree and is not globbed here.) `panel_sanitizer` already flags these as
    `hardcoded_campaign`. Whether a frozen list is intended (a stable datum) or
    accidental (literals nobody templated) is a PHIVOLCS decision; this test
    exists so the answer stops being invisible.
    """
    refs = {}
    for panel in sorted(REAL_PANELS.glob("*/ADDNEQ2.INP")):
        _, fix = extract_freesta_reference(
            panel.read_text(encoding="utf-8", errors="replace")
        )
        refs[panel.parent.name] = fix.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]

    assert refs.get("R2S_FIN") == "REF190110.FIX"
    assert sum(1 for v in refs.values() if v == "REF190110.FIX") >= 4
    assert refs.get("PHI_WK") == "REF192560.FIX"
