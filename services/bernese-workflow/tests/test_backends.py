"""Tests for BPE backend implementations — no Perl, no filesystem side effects."""
from __future__ import annotations

import pytest
from bernese_workflow.backends import (
    LinuxBPEBackend,
    WindowsBPEBackend,
    _parse_bpe_output,
)

# ---------------------------------------------------------------------------
# _parse_bpe_output
# ---------------------------------------------------------------------------

def test_bpe_result_success():
    result = _parse_bpe_output("processing...\nBPE finished\n")
    assert result.success is True


def test_bpe_result_aborted():
    result = _parse_bpe_output("BPE aborted\n")
    assert result.success is False


def test_bpe_result_crashed():
    result = _parse_bpe_output("BPE crashed with error\n")
    assert result.success is False


def test_parse_stations_survived():
    result = _parse_bpe_output("Stations accepted: 12\nBPE finished\n")
    assert result.stations_survived == 12


def test_parse_fixing_rate_decimal():
    result = _parse_bpe_output("Fixing rate: 0.823\nBPE finished\n")
    assert result.ambiguity_fixing_rate == pytest.approx(0.823, abs=1e-4)


def test_parse_fixing_rate_percent():
    result = _parse_bpe_output("Fixing rate: 82.3 %\nBPE finished\n")
    assert result.ambiguity_fixing_rate == pytest.approx(0.823, abs=1e-4)


def test_helmchk_failed():
    result = _parse_bpe_output("HELMCHK: failed\nBPE finished\n")
    assert result.helmchk_failed is True


def test_comparf_ok():
    result = _parse_bpe_output("COMPARF: ok\nBPE finished\n")
    assert result.comparf_failed is False


def test_missing_metrics_are_none():
    result = _parse_bpe_output("BPE finished\n")
    assert result.stations_survived is None
    assert result.ambiguity_fixing_rate is None
    assert result.helmchk_failed is False
    assert result.comparf_failed is False


# ---------------------------------------------------------------------------
# LinuxBPEBackend.prepare_campaign
# ---------------------------------------------------------------------------

def test_linux_backend_prepare_creates_subdirs(tmp_path):
    backend = LinuxBPEBackend(
        bernese_root=tmp_path / "BERN54",
        user_dir=tmp_path / "GPSUSER",
        campaign_dir=tmp_path / "GPSDATA",
    )
    backend.prepare_campaign("TESTCAMP", 2023, "0100")

    campaign_path = tmp_path / "GPSDATA" / "TESTCAMP"
    for subdir in ("ATM", "BPE", "GRD", "OBS", "ORB", "ORX", "OUT", "RAW", "SOL", "STA"):
        assert (campaign_path / subdir).is_dir(), f"Missing subdir: {subdir}"


# ---------------------------------------------------------------------------
# WindowsBPEBackend
# ---------------------------------------------------------------------------

def test_windows_backend_raises_not_implemented():
    backend = WindowsBPEBackend()
    with pytest.raises(NotImplementedError):
        backend.run("CAMP", 2023, "0100")
