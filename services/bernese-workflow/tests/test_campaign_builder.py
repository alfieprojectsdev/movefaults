"""Tests for campaign file generators and LinuxBPEBackend.prepare_campaign."""
from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest
from bernese_workflow.campaign_builder import (
    generate_abb,
    generate_clu,
    generate_crd,
    generate_sta,
    generate_vel,
)
from bernese_workflow.campaign_models import CampaignConfig, StationRecord

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

BOST = StationRecord(
    name="BOST",
    x=-3186600.123,
    y=5765432.679,
    z=567890.456,
    vx=0.00500,
    vy=-0.01200,
    vz=0.00300,
    receiver="LEICA GR50",
    antenna="LEIAR20",
)

PBIS = StationRecord(
    name="PBIS",
    x=-3100000.000,
    y=5700000.000,
    z=600000.000,
    vx=0.00410,
    vy=-0.01100,
    vz=0.00280,
)

STATIONS = [BOST, PBIS]


# ---------------------------------------------------------------------------
# STA file
# ---------------------------------------------------------------------------

def test_sta_contains_all_station_names():
    content = generate_sta(STATIONS)
    assert "BOST" in content
    assert "PBIS" in content


def test_sta_has_type001_and_type002():
    content = generate_sta(STATIONS)
    assert "TYPE 001: RENAMING OF STATIONS" in content
    assert "TYPE 002: STATION INFORMATION" in content


def test_sta_type001_uses_wildcard_old_name():
    content = generate_sta(STATIONS)
    # TYPE 001 uses XXXX* wildcard for old station name
    assert "BOST*" in content
    assert "PBIS*" in content


def test_sta_type002_includes_receiver_and_antenna():
    content = generate_sta(STATIONS)
    assert "LEICA GR50" in content
    assert "LEIAR20" in content


# ---------------------------------------------------------------------------
# CRD file
# ---------------------------------------------------------------------------

def test_crd_contains_coordinates():
    content = generate_crd(STATIONS)
    # X coordinate appears (with some precision)
    assert "-3186600" in content
    assert "5765432" in content


def test_crd_has_datum_header():
    content = generate_crd(STATIONS, ref_frame="IGS14", epoch="2015-01-01 00:00:00")
    assert "IGS14" in content
    assert "2015-01-01" in content


def test_crd_sequential_station_numbers():
    content = generate_crd(STATIONS)
    assert re.search(r"\s+1\s+BOST", content) is not None
    assert re.search(r"\s+2\s+PBIS", content) is not None


# ---------------------------------------------------------------------------
# ABB file
# ---------------------------------------------------------------------------

def test_abb_contains_4id_and_2id():
    content = generate_abb(STATIONS)
    assert "BOST" in content
    assert "BO" in content
    assert "PBIS" in content
    assert "PB" in content


# ---------------------------------------------------------------------------
# VEL file
# ---------------------------------------------------------------------------

def test_vel_contains_velocities():
    content = generate_vel(STATIONS)
    # VX for BOST should appear
    assert "0.00500" in content


def test_vel_has_datum_header():
    content = generate_vel(STATIONS, ref_frame="IGS14")
    assert "IGS14" in content


# ---------------------------------------------------------------------------
# CLU file
# ---------------------------------------------------------------------------

def test_clu_assigns_all_stations_to_cpu1():
    content = generate_clu(STATIONS)
    lines = [row for row in content.splitlines() if "BOST" in row or "PBIS" in row]
    assert len(lines) == 2
    for line in lines:
        assert line.strip().endswith("1")


# ---------------------------------------------------------------------------
# LinuxBPEBackend.prepare_campaign — file generation path
# ---------------------------------------------------------------------------

def test_prepare_campaign_generates_all_files(tmp_path):
    from bernese_workflow.backends import LinuxBPEBackend

    backend = LinuxBPEBackend(
        bernese_root=tmp_path / "BERN54",
        user_dir=tmp_path / "GPSUSER",
        campaign_dir=tmp_path / "GPSDATA",
    )
    config = CampaignConfig(
        campaign_name="TESTCAMP",
        year=2023,
        session="0100",
        stations=STATIONS,
        download_blq=False,  # skip network call in tests
    )
    backend.prepare_campaign("TESTCAMP", 2023, "0100", config=config)

    sta_dir = tmp_path / "GPSDATA" / "TESTCAMP" / "STA"
    for ext in (".STA", ".CRD", ".ABB", ".VEL", ".CLU"):
        path = sta_dir / f"TESTCAMP{ext}"
        assert path.exists(), f"Missing: {path.name}"


def test_prepare_campaign_crd_content(tmp_path):
    from bernese_workflow.backends import LinuxBPEBackend

    backend = LinuxBPEBackend(
        bernese_root=tmp_path / "BERN54",
        user_dir=tmp_path / "GPSUSER",
        campaign_dir=tmp_path / "GPSDATA",
    )
    config = CampaignConfig(
        campaign_name="TESTCAMP",
        year=2023,
        session="0100",
        stations=STATIONS,
        download_blq=False,
    )
    backend.prepare_campaign("TESTCAMP", 2023, "0100", config=config)

    crd = (tmp_path / "GPSDATA" / "TESTCAMP" / "STA" / "TESTCAMP.CRD").read_text()
    assert "BOST" in crd
    assert "-3186600" in crd


def test_prepare_campaign_no_config_still_creates_subdirs(tmp_path):
    from bernese_workflow.backends import _SUBDIRS, LinuxBPEBackend

    backend = LinuxBPEBackend(
        bernese_root=tmp_path / "BERN54",
        user_dir=tmp_path / "GPSUSER",
        campaign_dir=tmp_path / "GPSDATA",
    )
    backend.prepare_campaign("CAMP2", 2023, "0100")  # no config

    for sub in _SUBDIRS:
        assert (tmp_path / "GPSDATA" / "CAMP2" / sub).is_dir()


# ---------------------------------------------------------------------------
# LinuxBPEBackend.run_continuous — two-pass logic
# ---------------------------------------------------------------------------

def test_run_continuous_calls_run_twice(tmp_path):
    from unittest.mock import MagicMock

    from bernese_workflow.backends import BPEResult, LinuxBPEBackend

    backend = LinuxBPEBackend(
        bernese_root=tmp_path / "BERN54",
        user_dir=tmp_path / "GPSUSER",
        campaign_dir=tmp_path / "GPSDATA",
    )

    # Create campaign directory so FIN_*.CRD lookup doesn't error
    out_dir = tmp_path / "GPSDATA" / "TESTCAMP" / "OUT"
    out_dir.mkdir(parents=True)
    sta_dir = tmp_path / "GPSDATA" / "TESTCAMP" / "STA"
    sta_dir.mkdir(parents=True)

    mock_snx = out_dir / "F1_0100.SNX"
    mock_snx.write_text("")

    pass1_result = BPEResult(
        success=True,
        stations_survived=2,
        ambiguity_fixing_rate=0.88,
        helmchk_failed=False,
        comparf_failed=False,
        output_files={"sinex": mock_snx},
    )
    pass2_result = BPEResult(
        success=True,
        stations_survived=2,
        ambiguity_fixing_rate=0.90,
        helmchk_failed=False,
        comparf_failed=False,
        output_files={"sinex": mock_snx},
    )
    backend.run = MagicMock(side_effect=[pass1_result, pass2_result])

    r1, r2 = backend.run_continuous("TESTCAMP", 2023, "0100")

    assert backend.run.call_count == 2
    assert r1.ambiguity_fixing_rate == pytest.approx(0.88)
    assert r2.ambiguity_fixing_rate == pytest.approx(0.90)


def test_run_continuous_raises_on_pass1_failure(tmp_path):
    from bernese_workflow.backends import BPEResult, LinuxBPEBackend

    backend = LinuxBPEBackend(
        bernese_root=tmp_path / "BERN54",
        user_dir=tmp_path / "GPSUSER",
        campaign_dir=tmp_path / "GPSDATA",
    )

    failed_result = BPEResult(
        success=False,
        stations_survived=None,
        ambiguity_fixing_rate=None,
        helmchk_failed=False,
        comparf_failed=False,
    )
    backend.run = MagicMock(return_value=failed_result)

    with pytest.raises(RuntimeError, match="pass 1 failed"):
        backend.run_continuous("TESTCAMP", 2023, "0100")

    # run() should have been called exactly once (no pass 2)
    backend.run.assert_called_once()
