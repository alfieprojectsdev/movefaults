"""Tests for BPE backend implementations — no Perl, no filesystem side effects."""
from __future__ import annotations

import pytest
from bernese_workflow.backends import (
    _SUBDIRS,
    LinuxBPEBackend,
    WindowsBPEBackend,
    _count_crd_stations,
    _parse_bpe_output,
    compute_maxpar,
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
    for subdir in _SUBDIRS:
        assert (campaign_path / subdir).is_dir(), f"Missing subdir: {subdir}"


# ---------------------------------------------------------------------------
# LinuxBPEBackend.collect_outputs
# ---------------------------------------------------------------------------

def test_collect_outputs_single_match(tmp_path):
    backend = LinuxBPEBackend(
        bernese_root=tmp_path / "BERN54",
        user_dir=tmp_path / "GPSUSER",
        campaign_dir=tmp_path / "GPSDATA",
    )
    out_dir = tmp_path / "GPSDATA" / "TESTCAMP" / "OUT"
    out_dir.mkdir(parents=True)
    (out_dir / "F1_0100.SNX").write_text("")
    (out_dir / "R1_0100.NQ0").write_text("")

    result = backend.collect_outputs("TESTCAMP", 2023, "0100")
    assert "sinex" in result
    assert "nq0" in result


def test_collect_outputs_raises_on_ambiguous(tmp_path):
    backend = LinuxBPEBackend(
        bernese_root=tmp_path / "BERN54",
        user_dir=tmp_path / "GPSUSER",
        campaign_dir=tmp_path / "GPSDATA",
    )
    out_dir = tmp_path / "GPSDATA" / "TESTCAMP" / "OUT"
    out_dir.mkdir(parents=True)
    (out_dir / "F1_0100.SNX").write_text("")
    (out_dir / "F1_0101.SNX").write_text("")

    with pytest.raises(RuntimeError, match="Ambiguous"):
        backend.collect_outputs("TESTCAMP", 2023, "0100")


def test_collect_outputs_empty(tmp_path):
    backend = LinuxBPEBackend(
        bernese_root=tmp_path / "BERN54",
        user_dir=tmp_path / "GPSUSER",
        campaign_dir=tmp_path / "GPSDATA",
    )
    out_dir = tmp_path / "GPSDATA" / "TESTCAMP" / "OUT"
    out_dir.mkdir(parents=True)

    result = backend.collect_outputs("TESTCAMP", 2023, "0100")
    assert result == {}


# ---------------------------------------------------------------------------
# compute_maxpar (gap #10)
# ---------------------------------------------------------------------------

def test_compute_maxpar_floor_for_small_networks():
    # 10 stations × 4 + 500 = 540, below the 1000 floor → clamped to 1000.
    assert compute_maxpar(10) == 1000


def test_compute_maxpar_scales_above_floor():
    # 270-station PAGENET: 270×4 + 500 = 1580, above the 1000 default.
    assert compute_maxpar(270) == 1580


def test_compute_maxpar_zero_is_floor():
    assert compute_maxpar(0) == 1000


def test_compute_maxpar_negative_raises():
    with pytest.raises(ValueError, match="n_stations"):
        compute_maxpar(-1)


# ---------------------------------------------------------------------------
# _count_crd_stations
# ---------------------------------------------------------------------------

_SAMPLE_CRD = """\
PAGENET CRD                                            07-JUL-26 12:00
--------------------------------------------------------------------------------
LOCAL GEODETIC DATUM: IGS14             EPOCH: 2026-03-28 00:00:00

NUM  STATION NAME           X (M)          Y (M)          Z (M)     FLAG
  1  ABMF 97103M001    2919785.71159  -5383745.06256  1774604.71308    A
  2  PZAM 00000M000    -3520000.00000  4900000.00000  1200000.00000    A
  3  CUSV 00000M000    -1200000.00000  6100000.00000  1600000.00000    A
"""


def test_count_crd_stations(tmp_path):
    crd = tmp_path / "PAGENET.CRD"
    crd.write_text(_SAMPLE_CRD)
    assert _count_crd_stations(crd) == 3


def test_count_crd_stations_missing_file(tmp_path):
    assert _count_crd_stations(tmp_path / "nope.CRD") == 0


# ---------------------------------------------------------------------------
# run() parameterization (gap #3 / task E) — no real Perl
# ---------------------------------------------------------------------------

class _FakeProc:
    def __init__(self):
        self.stdout = "BPE finished\n"
        self.stderr = ""


def test_run_exports_parameterized_bpe_vars(tmp_path, monkeypatch):
    """PCF_FILE / CPU_FILE / driver argv / MAXPAR flow from constructor → subprocess."""
    captured: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs["env"]
        return _FakeProc()

    monkeypatch.setattr("bernese_workflow.backends.subprocess.run", fake_run)

    # Campaign CRD with 3 stations so MAXPAR is auto-sized (floored to 1000).
    camp = tmp_path / "GPSDATA" / "PAGENET"
    (camp / "STA").mkdir(parents=True)
    (camp / "STA" / "PAGENET.CRD").write_text(_SAMPLE_CRD)

    backend = LinuxBPEBackend(
        bernese_root=tmp_path / "BERN54",
        user_dir=tmp_path / "GPSUSER",
        campaign_dir=tmp_path / "GPSDATA",
        pcf_file="PAGENET_DLY",
        cpu_file="USER",
        driver_script=tmp_path / "GPSUSER" / "SCRIPT" / "pagenet_pcs.pl",
    )
    backend.run("PAGENET", 2026, "0870")

    env = captured["env"]
    assert env["PCF_FILE"] == "PAGENET_DLY"
    assert env["CPU_FILE"] == "USER"
    assert env["BPE_CAMPAIGN"] == "PAGENET"
    assert env["MAXPAR"] == "1000"  # 3 sta → floored
    # PCF passed as argv[2]; driver script honored.
    assert captured["cmd"][-1] == "PAGENET_DLY"
    assert str(captured["cmd"][1]).endswith("pagenet_pcs.pl")


def test_run_explicit_max_par_overrides_crd_count(tmp_path, monkeypatch):
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "bernese_workflow.backends.subprocess.run",
        lambda cmd, **kw: captured.update(env=kw["env"]) or _FakeProc(),
    )

    camp = tmp_path / "GPSDATA" / "PAGENET"
    (camp / "STA").mkdir(parents=True)
    (camp / "STA" / "PAGENET.CRD").write_text(_SAMPLE_CRD)

    backend = LinuxBPEBackend(
        bernese_root=tmp_path / "BERN54",
        user_dir=tmp_path / "GPSUSER",
        campaign_dir=tmp_path / "GPSDATA",
        max_par=4096,
    )
    backend.run("PAGENET", 2026, "0870")
    assert captured["env"]["MAXPAR"] == "4096"


def test_run_omits_maxpar_when_uncomputable(tmp_path, monkeypatch):
    """No CRD, no override → no MAXPAR injected (panel/PCF default stands)."""
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "bernese_workflow.backends.subprocess.run",
        lambda cmd, **kw: captured.update(env=kw["env"]) or _FakeProc(),
    )

    (tmp_path / "GPSDATA" / "NOCRD" / "STA").mkdir(parents=True)
    backend = LinuxBPEBackend(
        bernese_root=tmp_path / "BERN54",
        user_dir=tmp_path / "GPSUSER",
        campaign_dir=tmp_path / "GPSDATA",
    )
    backend.run("NOCRD", 2026, "0870")
    assert "MAXPAR" not in captured["env"]


def test_run_defaults_preserve_stock_contract(tmp_path, monkeypatch):
    """Unconfigured backend still drives RNX2SNX via the stock driver."""
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "bernese_workflow.backends.subprocess.run",
        lambda cmd, **kw: captured.update(cmd=cmd, env=kw["env"]) or _FakeProc(),
    )

    (tmp_path / "GPSDATA" / "CAMP" / "STA").mkdir(parents=True)
    backend = LinuxBPEBackend(
        bernese_root=tmp_path / "BERN54",
        user_dir=tmp_path / "GPSUSER",
        campaign_dir=tmp_path / "GPSDATA",
    )
    backend.run("CAMP", 2023, "0100")
    assert captured["env"]["PCF_FILE"] == "RNX2SNX"
    assert captured["env"]["CPU_FILE"] == "USER"
    assert str(captured["cmd"][1]).endswith("rnx2snx_pcs.pl")


# ---------------------------------------------------------------------------
# WindowsBPEBackend
# ---------------------------------------------------------------------------

def test_windows_backend_raises_not_implemented():
    backend = WindowsBPEBackend()
    with pytest.raises(NotImplementedError):
        backend.run("CAMP", 2023, "0100")
