"""PCFContext, and the GPSEST troposphere drift check (GEO-003)."""
import re
from pathlib import Path

import pytest
from bernese_workflow.pcf_context import (
    LUZON_TROPOSPHERE,
    PCFContext,
    TroposphereSettings,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
# The repo's **5.2** panel set. Deliberately named so, because it is NOT the
# tree the R740 runs: the live 5.4 tree at $U/OPT carries WET_GMF3 in R2S_EDT
# and R2S_FIN where this one carries WET_GMF. A test against this path proves
# the committed 5.2 config is stable and proves nothing about production.
# See the note above LUZON_TROPOSPHERE in pcf_context.py.
LUZON_OPT_52 = REPO_ROOT / "config" / "bernese" / "gpsuser52-luzon" / "OPT"
LUZON_OPT = LUZON_OPT_52  # back-compat for the existing tests below

# GPSEST panel line:  MAPPNG 1  "WET_GMF"
_PANEL_VALUE = re.compile(r'^\s*(?P<key>[A-Z0-9_]+)\s+\d+\s+"(?P<value>[^"]*)"')


def _read_troposphere(panel: Path) -> TroposphereSettings:
    """Pull MAPPNG / NUMPAR / NUMGRD out of a real GPSEST.INP."""
    found: dict[str, str] = {}
    for line in panel.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _PANEL_VALUE.match(line)
        if m and m.group("key") in {"MAPPNG", "NUMPAR", "NUMGRD"}:
            found.setdefault(m.group("key"), m.group("value").strip())
    missing = {"MAPPNG", "NUMPAR", "NUMGRD"} - set(found)
    if missing:
        raise AssertionError(f"{panel} is missing {sorted(missing)}")
    return TroposphereSettings(found["MAPPNG"], found["NUMPAR"], found["NUMGRD"])


# ---------------------------------------------------------------------------
# PCFContext itself
# ---------------------------------------------------------------------------

def test_to_dict_stringifies_every_field():
    d = PCFContext(v_crdinf="PIVSMIND", v_rnxdir="PIVSMIND").to_dict()
    assert all(isinstance(v, str) for v in d.values())
    assert d["v_crdinf"] == "PIVSMIND"


def test_clustering_defaults_are_unchanged():
    """RH-006 plumbing. v_clufin='A' is the untuned value pending the R740."""
    d = PCFContext(v_crdinf="X", v_rnxdir="Y").to_dict()
    assert d["v_clu"] == "10"
    assert d["v_clufin"] == "A"


# ---------------------------------------------------------------------------
# Troposphere drift
# ---------------------------------------------------------------------------

def test_declared_table_covers_every_gpsest_panel():
    panels = {p.parent.name for p in LUZON_OPT.glob("*/GPSEST.INP")}
    assert panels, "expected GPSEST panels under the Luzon OPT tree"
    assert panels == set(LUZON_TROPOSPHERE), (
        "LUZON_TROPOSPHERE and the committed panels disagree about which "
        f"panels exist: only in panels {sorted(panels - set(LUZON_TROPOSPHERE))}, "
        f"only in table {sorted(set(LUZON_TROPOSPHERE) - panels)}"
    )


@pytest.mark.parametrize("panel_name", sorted(LUZON_TROPOSPHERE))
def test_declared_settings_match_the_committed_panel(panel_name):
    """The declared table must describe the panels as they actually are.

    This is the whole value of GEO-003 at this stage. The GMF/Niell split and
    the 01:00:00-vs-02:00:00 interval difference were found by reading six
    files by hand; this makes any further drift fail a test instead.

    If you are changing a panel deliberately, update the table in the same
    commit and say why in the message — that is the point, not an obstacle.
    """
    actual = _read_troposphere(LUZON_OPT / panel_name / "GPSEST.INP")
    assert actual == LUZON_TROPOSPHERE[panel_name]


def test_the_known_divergence_is_still_present_and_recorded():
    """Pins GEO-002's finding so it cannot be quietly 'fixed' unrecorded.

    Three mapping functions across six panels, and R2S_FIN estimating zenith
    delay at a different interval from everything upstream. Both are real and
    currently undocumented as deliberate. When GEO-002 resolves, this test
    should be updated in the same change that makes the panels agree.
    """
    mapping_functions = {s.mappng for s in LUZON_TROPOSPHERE.values()}
    assert mapping_functions == {"COSZ", "WET_GMF", "WET_NIELL"}

    assert LUZON_TROPOSPHERE["R2S_FIN"].numpar == "01 00 00"
    upstream = {
        name: s.numpar for name, s in LUZON_TROPOSPHERE.items() if name != "R2S_FIN"
    }
    assert set(upstream.values()) == {"02 00 00"}


def test_final_solve_is_not_coarser_than_gsi_mindanao():
    """Guard against 'shorten the troposphere interval' being reapplied.

    That advice was wrong and was retracted: R2S_FIN already estimates hourly,
    shorter than the 3-hourly GSI used on PHIVOLCS' own Mindanao data
    (Tobita et al. 2015). This fails if anyone lengthens it past 3 hours.
    """
    hh, mm, ss = (int(x) for x in LUZON_TROPOSPHERE["R2S_FIN"].numpar.split())
    assert hh * 3600 + mm * 60 + ss <= 3 * 3600


def test_the_declared_table_is_documented_as_describing_the_52_tree():
    """Guards the correction of 2026-08-24, not a value.

    The troposphere table was measured from the 5.2 config while the R740 runs
    a 5.4 tree whose float and final panels use WET_GMF3, not WET_GMF. The
    drift test above could never have caught that: it compares the table
    against the same 5.2 files the table was read from.

    That is not a reason to delete the test -- pinning the 5.2 config is
    worth doing. It is a reason to make the scope explicit, so nobody reads a
    passing suite as evidence about production. This asserts the explanation
    stays attached to the code.
    """
    src = (
        REPO_ROOT / "services" / "bernese-workflow" / "src" / "bernese_workflow"
        / "pcf_context.py"
    ).read_text(encoding="utf-8")
    assert "WET_GMF3" in src, (
        "the note recording that the live 5.4 tree uses WET_GMF3 has been "
        "removed from pcf_context.py -- restore it or record the decision "
        "that superseded it"
    )
    assert "LIVE 5.4 tree" in src
