"""Tests for the `offsets` discontinuity-catalog loader and validator."""
from pathlib import Path

import pytest
from pogf_geodetic_suite.timeseries.analysis import OffsetType
from pogf_geodetic_suite.timeseries.offsets_catalog import (
    load_offsets_catalog,
    validate_offsets_catalog,
)

# The real catalog, four levels up from this test file.
REAL_CATALOG = (
    Path(__file__).resolve().parents[3]
    / "docs" / "bern52" / "phivolcs-scripts" / "event-catalog" / "offsets"
)


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "offsets"
    p.write_text(body, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_load_groups_by_station(tmp_path):
    cat = load_offsets_catalog(_write(tmp_path, (
        "AAAA 2019.1000 EQ\n"
        "BBBB 2020.2000 CE\n"
        "AAAA 2021.3000 UK\n"
    )))
    assert set(cat) == {"AAAA", "BBBB"}
    assert len(cat["AAAA"]) == 2
    assert cat["BBBB"][0].offset_type is OffsetType.CE


def test_load_sorts_out_of_order_records(tmp_path):
    """The loader sorts, so a consumer cannot be bitten by file ordering."""
    cat = load_offsets_catalog(_write(tmp_path, (
        "AAAA 2022.8159 EQ\n"
        "AAAA 2022.5695 EQ\n"
    )))
    assert [e.date for e in cat["AAAA"]] == [2022.5695, 2022.8159]


def test_load_skips_blank_and_comment_lines(tmp_path):
    cat = load_offsets_catalog(_write(tmp_path, (
        "# header comment\n"
        "\n"
        "AAAA 2019.1000 EQ   # trailing comment\n"
        "   \n"
    )))
    assert len(cat["AAAA"]) == 1


def test_load_accepts_crlf(tmp_path):
    """The real catalog is CRLF. Reading it must not depend on that."""
    p = tmp_path / "offsets"
    p.write_bytes(b"AAAA 2019.1000 EQ\r\nBBBB 2020.2000 EQ")
    cat = load_offsets_catalog(p)
    assert set(cat) == {"AAAA", "BBBB"}


def test_load_raises_on_short_line(tmp_path):
    with pytest.raises(ValueError, match="expected 'STATION EPOCH TYPE'"):
        load_offsets_catalog(_write(tmp_path, "AAAA 2019.1000\n"))


def test_load_raises_on_unknown_type_and_names_the_line(tmp_path):
    with pytest.raises(ValueError, match=r"offsets:2: unknown offset type 'ZZ'"):
        load_offsets_catalog(_write(tmp_path, (
            "AAAA 2019.1000 EQ\n"
            "BBBB 2020.2000 ZZ\n"
        )))


def test_load_raises_on_non_numeric_epoch(tmp_path):
    with pytest.raises(ValueError, match="not a decimal year"):
        load_offsets_catalog(_write(tmp_path, "AAAA notayear EQ\n"))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_validate_clean_catalog_returns_nothing(tmp_path):
    findings = validate_offsets_catalog(_write(tmp_path, (
        "AAAA 2019.1000 EQ\n"
        "AAAA 2021.3000 EQ\n"
        "BBBB 2020.2000 CE\n"
    )))
    assert findings == []


def test_validate_flags_out_of_order_within_a_station(tmp_path):
    """The defect that makes the MATLAB fit stale timestamps."""
    findings = validate_offsets_catalog(_write(tmp_path, (
        "AAAA 2022.8159 EQ\n"
        "AAAA 2022.5695 EQ\n"
    )))
    assert len(findings) == 1
    assert findings[0].kind == "out_of_order"
    assert findings[0].line == 2
    assert findings[0].station == "AAAA"


def test_validate_does_not_flag_interleaved_stations(tmp_path):
    """Ordering is per station. A later station starting earlier is fine."""
    findings = validate_offsets_catalog(_write(tmp_path, (
        "AAAA 2022.8000 EQ\n"
        "BBBB 2001.1000 EQ\n"
    )))
    assert findings == []


def test_validate_flags_duplicates(tmp_path):
    findings = validate_offsets_catalog(_write(tmp_path, (
        "AAAA 2019.1000 EQ\n"
        "AAAA 2019.1000 EQ\n"
    )))
    assert [f.kind for f in findings] == ["duplicate"]


def test_validate_flags_implausible_epoch(tmp_path):
    findings = validate_offsets_catalog(_write(tmp_path, "AAAA 1776.0000 EQ\n"))
    assert [f.kind for f in findings] == ["bad_epoch"]


def test_validate_reports_every_problem_not_just_the_first(tmp_path):
    """Unlike the loader, validation does not stop at the first bad line."""
    findings = validate_offsets_catalog(_write(tmp_path, (
        "AAAA 2019.1000 EQ\n"
        "BBBB oops EQ\n"
        "CCCC 2020.0000 ZZ\n"
        "AAAA 2018.0000 EQ\n"
    )))
    kinds = sorted(f.kind for f in findings)
    assert kinds == ["malformed", "out_of_order", "unknown_type"]


# ---------------------------------------------------------------------------
# The real catalog
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not REAL_CATALOG.exists(), reason="catalog not present")
def test_real_catalog_is_clean():
    """Regression guard on the committed catalog.

    BR14 and LUZD each listed 2022.8159 before 2022.5695. `analysis.py` sorts
    and was unaffected, but the MATLAB PHIVOLCS still runs builds segment
    bounds in file order: a descending range leaves the previous segment's
    design matrix in place and fits stale timestamps against current data,
    silently. Both were corrected; this keeps them corrected.
    """
    findings = validate_offsets_catalog(REAL_CATALOG)
    assert findings == [], "\n".join(str(f) for f in findings)


@pytest.mark.skipif(not REAL_CATALOG.exists(), reason="catalog not present")
def test_real_catalog_loads_and_covers_the_known_stations():
    cat = load_offsets_catalog(REAL_CATALOG)
    assert len(cat) == 70
    assert sum(len(v) for v in cat.values()) == 89
    assert [e.date for e in cat["BR14"]] == [2022.5695, 2022.8159]
    assert [e.date for e in cat["LUZD"]] == [2022.5695, 2022.8159]
