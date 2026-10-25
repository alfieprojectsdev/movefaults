"""Tests for BPE backend implementations — no Perl, no filesystem side effects."""
from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest
from bernese_workflow import backends
from bernese_workflow.backends import (
    _SUBDIRS,
    LinuxBPEBackend,
    WindowsBPEBackend,
    _count_crd_stations,
    _parse_bpe_output,
    _run_bpe_process,
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

    monkeypatch.setattr("bernese_workflow.backends._run_bpe_process", fake_run)

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
        "bernese_workflow.backends._run_bpe_process",
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
        "bernese_workflow.backends._run_bpe_process",
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
        "bernese_workflow.backends._run_bpe_process",
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


# ---------------------------------------------------------------------------
# _run_bpe_process: a timeout kills the whole BPE, not just the driver
# ---------------------------------------------------------------------------

def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A reaped-later zombie still answers kill(0); it is dead for our purposes.
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().split(")")[-1].split()[0] != "Z"
    except FileNotFoundError:
        return False


def _gone_within(pid: int, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.05)
    return not _alive(pid)


@pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="process groups; _alive reads /proc"
)
def test_timeout_kills_jobs_started_the_way_the_cpu_file_starts_them(tmp_path, monkeypatch):
    """USER.CPU launches jobs as `echo '<COMMAND>' | sh &`: grandchildren of the
    driver. subprocess.run's timeout killed only the driver and left them running."""
    monkeypatch.setattr(backends, "_KILL_GRACE_SEC", 1)
    pidfile = tmp_path / "job.pid"
    driver = tmp_path / "driver.sh"
    driver.write_text(
        "#!/bin/sh\n"
        f"echo 'echo $$ > {pidfile}; exec sleep 300' | sh &\n"
        "exec sleep 300\n"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        _run_bpe_process(["sh", str(driver)], env=dict(os.environ), timeout=3)

    job_pid = int(pidfile.read_text())
    assert _gone_within(job_pid, 5), "the BPE job outlived the timeout"


@pytest.mark.skipif(sys.platform == "win32", reason="process groups are POSIX")
def test_bpe_runs_in_its_own_group_so_the_kill_cannot_reach_the_caller():
    out = _run_bpe_process(
        [sys.executable, "-c", "import os; print(os.getpgrp())"],
        env=dict(os.environ),
        timeout=10,
    )
    assert out.returncode == 0
    assert int(out.stdout) != os.getpgrp()


def test_run_reports_a_killed_group_as_a_timeout(tmp_path, monkeypatch):
    def times_out(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])

    monkeypatch.setattr("bernese_workflow.backends._run_bpe_process", times_out)
    (tmp_path / "GPSDATA" / "CAMP" / "STA").mkdir(parents=True)
    backend = LinuxBPEBackend(
        bernese_root=tmp_path / "BERN54",
        user_dir=tmp_path / "GPSUSER",
        campaign_dir=tmp_path / "GPSDATA",
        timeout_sec=5,
    )
    with pytest.raises(RuntimeError, match="timed out after 5s.*process group was sent SIGTERM"):
        backend.run("CAMP", 2023, "0100")


@pytest.mark.skipif(sys.platform == "win32", reason="process groups are POSIX")
def test_timeout_keeps_the_partial_bpe_log(monkeypatch):
    monkeypatch.setattr(backends, "_KILL_GRACE_SEC", 1)
    with pytest.raises(subprocess.TimeoutExpired) as info:
        _run_bpe_process(
            ["sh", "-c", "echo PCF started; exec sleep 300"],
            env=dict(os.environ),
            timeout=1,
        )
    assert "PCF started" in info.value.stdout


@pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="process groups; _alive reads /proc"
)
def test_a_driver_that_exits_early_does_not_leave_its_jobs_running(tmp_path, monkeypatch):
    """A job that does not hold the output pipe lets communicate() return as soon
    as the driver exits. It is still in the driver's group and must not outlive
    the drain."""
    monkeypatch.setattr(backends, "_KILL_GRACE_SEC", 1)
    monkeypatch.setattr(backends, "_DRAIN_SEC", 1)
    pidfile = tmp_path / "job.pid"
    driver = tmp_path / "driver.sh"
    driver.write_text(
        "#!/bin/sh\n"
        f"echo 'echo $$ > {pidfile}; exec sleep 300' | sh >/dev/null 2>&1 &\n"
        f"while [ ! -s {pidfile} ]; do sleep 0.05; done\n"
        "exit 0\n"
    )
    out = _run_bpe_process(["sh", str(driver)], env=dict(os.environ), timeout=10)

    assert out.returncode == 0
    job_pid = int(pidfile.read_text())
    assert _gone_within(job_pid, 5), "a BPE job outlived its driver"


@pytest.mark.skipif(sys.platform == "win32", reason="process groups are POSIX")
def test_a_kill_that_is_refused_does_not_hide_the_timeout(monkeypatch):
    """EPERM from killpg must not replace the TimeoutExpired that run() turns
    into its 'BPE timed out' RuntimeError."""
    monkeypatch.setattr(backends, "_KILL_GRACE_SEC", 1)
    real_killpg = os.killpg
    started: list[int] = []

    def refuse(pgid, sig):
        started.append(pgid)
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(backends.os, "killpg", refuse)
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            _run_bpe_process(
                ["sh", "-c", "exec sleep 30"], env=dict(os.environ), timeout=1
            )
    finally:
        for pgid in started[:1]:
            try:
                real_killpg(pgid, 9)
            except ProcessLookupError:
                pass


def test_kill_group_reports_a_group_that_survives_sigkill(monkeypatch, caplog):
    """A member in uninterruptible sleep can outlive SIGKILL's grace. Say so,
    rather than returning as though the group were gone."""
    monkeypatch.setattr(backends, "_KILL_GRACE_SEC", 0.2)
    monkeypatch.setattr(backends.os, "killpg", lambda pgid, sig: None)

    class _Proc:
        pid = 4242

        def poll(self):
            return None

    with caplog.at_level("ERROR", logger="bernese_workflow.backends"):
        assert backends._kill_group(_Proc()) is False
    assert "4242" in caplog.text


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="reads /proc")
def test_bpe_does_not_inherit_the_callers_stdin():
    """A detached BPE must not read (or block on) whatever the caller's fd 0 is.
    fd 0 is swapped for a pipe first: under cron or pytest it is often already
    /dev/null, and then this test could not fail."""
    r, w = os.pipe()
    saved = os.dup(0)
    try:
        os.dup2(r, 0)
        out = _run_bpe_process(
            ["readlink", "/proc/self/fd/0"], env=dict(os.environ), timeout=10
        )
    finally:
        os.dup2(saved, 0)
        for fd in (saved, r, w):
            os.close(fd)
    assert out.stdout.strip() == "/dev/null"


@pytest.mark.skipif(sys.platform == "win32", reason="process groups are POSIX")
def test_a_job_still_finishing_when_the_driver_exits_is_not_killed(tmp_path, caplog):
    """BSW 5.4's server writes QUIT to a client and exits without waiting for it
    (t_script::stopClient), so the last RUNBPE client can still be removing its
    temp user area and writing its PRT tail after the driver returns. The sweep
    must let it finish, and must not warn about it."""
    marker = tmp_path / "prt_tail_written"
    driver = tmp_path / "driver.sh"
    driver.write_text(
        "#!/bin/sh\n"
        f"echo 'sleep 1; echo SCRIPT__ENDED > {marker}' | sh >/dev/null 2>&1 &\n"
        "exit 0\n"
    )
    with caplog.at_level("WARNING", logger="bernese_workflow.backends"):
        out = _run_bpe_process(["sh", str(driver)], env=dict(os.environ), timeout=10)

    assert out.returncode == 0
    assert marker.read_text().strip() == "SCRIPT__ENDED", "the sweep killed a finishing job"
    assert caplog.text == ""
