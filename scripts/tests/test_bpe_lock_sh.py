"""
scripts/bpe_lock.sh and bernese_workflow.bpe_lock must be ONE lock.

Before this, the scripts/ drivers each had a lock of their own and the
service had a machine-wide flock, so a service run and a shell run could
start on one machine together. Each test below runs the shell side for
real (bash + flock) against the Python side for real.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts" / "bpe_lock.sh"
sys.path.insert(0, str(ROOT / "services" / "bernese-workflow" / "src"))

from bernese_workflow.bpe_lock import BPELock, BPELockHeld  # noqa: E402

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None or shutil.which("flock") is None,
    reason="needs bash and flock(1)",
)


def _shell(lock: Path, body: str, **kw) -> subprocess.Popen:
    script = f'source "{HELPER}"\n{body}\n'
    env = {**os.environ, "BPE_LOCK": str(lock)}
    return subprocess.Popen(
        ["bash", "-c", script], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, **kw,
    )  # fmt: skip


def _wait_for(pred, timeout: float = 10.0) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return
        time.sleep(0.05)
    raise AssertionError("timed out")


def _held(lock: Path) -> bool:
    try:
        with BPELock(lock, purpose="probe"):
            return False
    except BPELockHeld:
        return True


def test_a_shell_holder_refuses_the_service_and_says_who(tmp_path: Path) -> None:
    lock = tmp_path / "bpe.lock"
    p = _shell(lock, 'bpe_lock_acquire "LUZON 2025 DOY 001-031" || exit 9; echo held; sleep 30')
    try:
        assert p.stdout.readline().strip() == "held"
        with pytest.raises(BPELockHeld, match="LUZON 2025 DOY 001-031"):
            with BPELock(lock, purpose="PHREF 2025"):
                pass
        rec = json.loads(lock.read_text())
        assert rec["pid"] == p.pid and rec["purpose"] == "LUZON 2025 DOY 001-031"
    finally:
        p.kill()
        p.wait()


def test_a_service_holder_refuses_the_shell_and_says_who(tmp_path: Path) -> None:
    lock = tmp_path / "bpe.lock"
    with BPELock(lock, purpose="PHREF 2025 091-120 (PHRPAR_DLY)"):
        p = _shell(lock, 'bpe_lock_acquire "LUZON month"; echo "rc=$?"')
        out, err = p.communicate(timeout=10)
    assert "rc=1" in out
    assert "PHREF 2025 091-120 (PHRPAR_DLY)" in err
    # The refused contender did not erase the holder's record.
    assert json.loads(lock.read_text())["purpose"] == "PHREF 2025 091-120 (PHRPAR_DLY)"


def test_the_lock_is_free_once_the_driver_and_its_children_exit(tmp_path: Path) -> None:
    lock = tmp_path / "bpe.lock"
    p = _shell(lock, 'bpe_lock_acquire "x" || exit 9')
    p.communicate(timeout=10)
    assert p.returncode == 0
    assert not _held(lock)


def test_a_bpe_left_running_by_a_killed_driver_keeps_the_machine_busy(tmp_path: Path) -> None:
    """The descriptor is inherited by what the driver starts. Kill the driver,
    and the 'BPE' it started still holds the lock: the machine is not free."""
    lock = tmp_path / "bpe.lock"
    marker = tmp_path / "child.pid"
    p = _shell(
        lock,
        f'bpe_lock_acquire "x" || exit 9; (sleep 30 & echo $! > "{marker}"; wait) & echo up; wait',
        start_new_session=True,
    )
    try:
        assert p.stdout.readline().strip() == "up"
        _wait_for(marker.exists)
        p.kill()  # the driver only; the background child lives on
        p.wait()
        assert _held(lock), "the child still holds it"
        os.kill(int(marker.read_text()), 9)
        _wait_for(lambda: not _held(lock))
    finally:
        try:
            os.killpg(p.pid, 9)
        except ProcessLookupError:
            pass


def test_a_purpose_with_quotes_still_writes_valid_json(tmp_path: Path) -> None:
    lock = tmp_path / "bpe.lock"
    p = _shell(lock, 'bpe_lock_acquire "say \\"hi\\" \\\\ there" || exit 9')
    p.communicate(timeout=10)
    assert json.loads(lock.read_text())["purpose"] == 'say "hi" \\ there'


@pytest.mark.skipif(not Path("/proc/locks").exists(), reason="Linux /proc/locks")
def test_local_ci_sees_the_lock_without_taking_it(tmp_path: Path) -> None:
    """local_ci defers while a BPE runs. It reads /proc/locks rather than trying
    the lock, which would make a run starting at that moment refuse."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("local_ci", ROOT / "scripts" / "local_ci.py")
    ci = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("local_ci", ci)  # dataclasses look the module up here
    spec.loader.exec_module(ci)

    lock = tmp_path / "bpe.lock"
    lock.touch()
    assert not ci.bpe_lock_held(lock)
    p = _shell(lock, 'bpe_lock_acquire "x" || exit 9; echo held; sleep 30')
    try:
        assert p.stdout.readline().strip() == "held"
        assert ci.bpe_lock_held(lock)
        assert not ci.bpe_lock_held(tmp_path / "other.lock")
    finally:
        p.kill()
        p.wait()
    assert not ci.bpe_lock_held(lock)


def _fake_bernese(home: Path) -> Path:
    """Just enough of a Bernese install for run_luzon_month.sh to reach its
    driver call; the 'driver' only leaves a marker that it was started."""
    for d in ("P", "U/PCF", "U/SCRIPT", "S"):
        (home / d).mkdir(parents=True)
    (home / "BERN54").mkdir()
    (home / "BERN54" / "LOADGPS.setvar").write_text(
        f'export P="{home}/P" U="{home}/U" S="{home}/S"\n'
    )
    (home / "U" / "PCF" / "LUZON_DLY.PCF").write_text("")
    marker = home / "driver-started"
    drv = home / "U" / "SCRIPT" / "luzon_pcs.pl"
    drv.write_text(f'#!/usr/bin/env perl\nopen(my $f, ">>", "{marker}"); print $f "x\\n";\n')
    drv.chmod(0o755)
    return marker


@pytest.mark.skipif(shutil.which("perl") is None, reason="needs perl")
def test_a_shell_driver_will_not_start_a_bpe_while_the_service_holds_the_lock(
    tmp_path: Path,
) -> None:
    """The end-to-end case: bernese-run-year holds the machine, and
    run_luzon_month.sh refuses before its driver runs. Then, with the lock
    free, the same invocation does reach the driver, so the refusal is the
    lock and not a broken fake."""
    home = tmp_path / "home"
    marker = _fake_bernese(home)
    lock = tmp_path / "bpe.lock"
    env = {**os.environ, "HOME": str(home), "BPE_LOCK": str(lock),
           "LUZON_DOY_FROM": "121", "LUZON_DOY_TO": "121", "LUZON_SKIP_DOYS": ""}  # fmt: skip
    cmd = ["bash", str(ROOT / "scripts" / "run_luzon_month.sh")]

    with BPELock(lock, purpose="PHREF 2025 091-120 (PHRPAR_DLY)"):
        r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode != 0
    assert "PHREF 2025 091-120 (PHRPAR_DLY)" in r.stderr
    assert not marker.exists(), "no BPE was started"

    subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
    assert marker.exists(), "with the lock free the driver is reached"
    assert not _held(lock), "and the lock is released when the run ends"
