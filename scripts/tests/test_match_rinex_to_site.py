"""Stage 3 must see the RINEX that the archive keeps inside zip bundles.

WHAT WAS WRONG, IN TWO LAYERS

The archive holds 15 zips. Six are Bernese software distributions and must be
ignored. Nine are RINEX bundles -- `ptgy223e.rnx.zip` and friends -- and they are
three real observation sessions stored in triplicate.

Each bundle holds four files in this order:

    ptgy223e.17g   GLONASS navigation   <- FIRST
    ptgy223e.17m   meteorological
    ptgy223e.17n   GPS navigation
    ptgy223e.17o   OBSERVATION          <- LAST

Two designs were on the table and both were wrong:

  * `main` skipped zips. But the skip was not where its comment said. The
    selection pattern `(\\.(gz|z))?` has no `zip`, so a `.rnx.zip` was never
    ENUMERATED -- it never reached the `PK` branch that claims to skip it. The
    three sessions vanished before anything could count them.

  * an abandoned branch read the FIRST member. In every one of the nine bundles
    that is the GLONASS nav file, so it would have misattributed all of them.

The fix is both halves together: select `.rnx.zip`, then read the member that
is actually an observation file -- and count every zip that cannot be read,
with the reason, rather than returning nothing in silence.
"""

from __future__ import annotations

import gzip
import importlib.util
import io
import zipfile
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "match_rinex_to_site.py"


@pytest.fixture(scope="module")
def m():
    spec = importlib.util.spec_from_file_location("match_rinex_to_site", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _reset_zip_outcomes(m):
    # Tolerant on purpose. Written as a bare `m.ZIP_OUTCOMES.clear()`, this
    # fixture ERRORED in setup for every test before the counter existed --
    # including the selection tests, which never touch it. Nineteen tests red
    # for one shared, harness-level reason is indistinguishable from nineteen
    # tests red for their own reasons, so the failing run said nothing about
    # which behaviour was missing. Each test must be able to fail on its own.
    counter = getattr(m, "ZIP_OUTCOMES", None)
    if counter is not None:
        counter.clear()
    yield


def _obs_header(marker: str) -> bytes:
    """A minimal RINEX 2 observation header, identifiable by its marker.

    Built with real fixed-width formatting, not typed by eye. RINEX header
    labels start at column 61 (index 60) and APPROX POSITION XYZ is three F14.4
    fields. The first version of this helper spaced the numbers by hand, put
    the label one column late, and the reader correctly refused it -- which
    showed up as a failing test of the ZIP code, when the zip code was right
    and the fixture was not valid RINEX.
    """
    def row(content: str, label: str) -> str:
        assert len(content) <= 60, "header content overflows its 60 columns"
        return f"{content:<60}{label}\n"

    xyz = f"{-3187302.1234:14.4f}{5288614.5678:14.4f}{1607829.9012:14.4f}"
    return (
        row("     2.11           OBSERVATION DATA    M (MIXED)", "RINEX VERSION / TYPE")
        + row(marker, "MARKER NAME")
        + row(xyz, "APPROX POSITION XYZ")
        + row("", "END OF HEADER")
    ).encode()


def _nav_header() -> bytes:
    """Something that is NOT an observation header, so reading it is detectable."""
    return b"     2.11           GLONASS NAV DATA                        RINEX VERSION / TYPE\n"


def _zip(path: Path, members: list[tuple[str, bytes]]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members:
            zf.writestr(name, data)
    return path


def _real_bundle(path: Path, marker: str = "PTGY") -> Path:
    """Exactly the shape of the nine archive bundles: observation file LAST."""
    stem = path.name.split(".")[0]
    return _zip(path, [
        (f"{stem}.17g", _nav_header()),
        (f"{stem}.17m", b"met data\n"),
        (f"{stem}.17n", b"gps nav\n"),
        (f"{stem}.17o", _obs_header(marker)),
    ])


# ---------------------------------------------------------------- selection

@pytest.mark.parametrize("name", ["ptgy223e.rnx.zip", "PTGY223E.RNX.ZIP", "abcd1230.17o.zip"])
def test_a_rinex_zip_is_selected(m, name):
    # The layer everyone missed: without this the bundles are never enumerated,
    # so no reader change can recover them.
    assert m._RINEX_NAME.search(name)


@pytest.mark.parametrize("name", ["exe_aiub_64_2021.zip", "update_2020-08-27.zip",
                                  "release_2012-12-14.zip"])
def test_a_software_zip_is_not_selected(m, name):
    # Six of the archive's 15 zips are Bernese distributions, not data.
    assert not m._RINEX_NAME.search(name)


@pytest.mark.parametrize("name", ["shao1850.09d.Z", "shao1850.09d.z", "abcd1230.17o.gz",
                                  "abcd1230.17o", "ABCD00PHL_R_20231230000_01D_30S_MO.crx.gz"])
def test_existing_forms_are_still_selected(m, name):
    # Widening the pattern must not narrow it: 28,679 files were once lost to
    # a missing lowercase `.z`.
    assert m._RINEX_NAME.search(name)


# ---------------------------------------------------------------- reading

def test_reads_the_observation_member_not_the_first(m, tmp_path):
    z = _real_bundle(tmp_path / "ptgy223e.rnx.zip", marker="PTGY")
    blob = m.header_bytes(z)
    assert b"MARKER NAME" in blob
    assert b"PTGY" in blob
    # The first member is the GLONASS nav file in every real bundle.
    assert b"GLONASS NAV DATA" not in blob


def test_read_header_attributes_the_bundle(m, tmp_path):
    z = _real_bundle(tmp_path / "ptgy223e.rnx.zip", marker="PTGY")
    xyz, marker, _year = m.read_header(z)
    assert marker.strip().upper().startswith("PTGY")
    assert xyz is not None


def test_a_bundle_that_is_read_is_counted(m, tmp_path):
    m.header_bytes(_real_bundle(tmp_path / "ptgy223e.rnx.zip"))
    assert m.ZIP_OUTCOMES["read"] == 1


# ---------------------------------------------------------------- refusals are counted, never silent

def test_no_observation_member_is_counted_not_silent(m, tmp_path):
    z = _zip(tmp_path / "navonly.rnx.zip", [("x.17g", _nav_header()), ("x.17n", b"nav\n")])
    assert m.header_bytes(z) == b""
    assert m.ZIP_OUTCOMES["skipped: no observation member"] == 1


def test_two_observation_members_are_not_guessed_between(m, tmp_path):
    # Picking one would be the first-member bug with a different tiebreak.
    z = _zip(tmp_path / "two.rnx.zip", [("a.17o", _obs_header("AAAA")),
                                        ("b.17o", _obs_header("BBBB"))])
    assert m.header_bytes(z) == b""
    assert m.ZIP_OUTCOMES["skipped: several observation members"] == 1


def test_a_corrupt_zip_is_counted_and_does_not_crash(m, tmp_path):
    bad = tmp_path / "broken.rnx.zip"
    bad.write_bytes(b"PK\x03\x04" + b"\x00" * 40)
    assert m.header_bytes(bad) == b""
    assert m.ZIP_OUTCOMES["skipped: unreadable zip"] == 1


def test_a_compressed_member_is_decompressed(m, tmp_path):
    z = _zip(tmp_path / "gz.rnx.zip", [("x.17g", _nav_header()),
                                       ("x.17o.gz", gzip.compress(_obs_header("GZIP")))])
    blob = m.header_bytes(z)
    assert b"GZIP" in blob and b"MARKER NAME" in blob
    assert m.ZIP_OUTCOMES["read"] == 1


def test_a_nested_zip_is_not_opened(m, tmp_path):
    # A .rnx.zip inside a .rnx.zip matches the pattern; recursing would make
    # the observation count depend on archive depth. Refuse, and say so.
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as zf:
        zf.writestr("x.17o", _obs_header("DEEP"))
    z = _zip(tmp_path / "outer.rnx.zip", [("inner.rnx.zip", inner.getvalue())])
    assert m.header_bytes(z) == b""
    assert m.ZIP_OUTCOMES["skipped: no observation member"] == 1
