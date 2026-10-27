"""Tests for bpe_lock: one BPE run at a time on a machine, enforced."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from bernese_workflow.bpe_lock import BPELock, BPELockHeld

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="fcntl locks are POSIX")


def test_a_second_holder_is_refused_and_told_who_holds_it(tmp_path: Path) -> None:
    lock = tmp_path / "bpe.lock"
    with BPELock(lock, purpose="PHREF 2025 152-181"):
        # A separate process, as a second run would be: flock is per open file
        # description, so a second open() in this process would also conflict,
        # but only another process shows the real refusal path.
        code = textwrap.dedent(
            f"""
            import sys
            sys.path.insert(0, {str(Path(__file__).resolve().parents[1] / "src")!r})
            from bernese_workflow.bpe_lock import BPELock, BPELockHeld
            try:
                with BPELock({str(lock)!r}, purpose="second"):
                    print("ACQUIRED")
            except BPELockHeld as e:
                print("REFUSED", e)
            """
        )
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.stdout.startswith("REFUSED"), r.stdout + r.stderr
    assert str(os.getpid()) in r.stdout
    assert "PHREF 2025 152-181" in r.stdout


def test_the_holder_is_recorded_while_held(tmp_path: Path) -> None:
    lock = tmp_path / "bpe.lock"
    with BPELock(lock, purpose="EXAMPLE 2023 010"):
        holder = json.loads(lock.read_text())
    assert holder["pid"] == os.getpid()
    assert holder["purpose"] == "EXAMPLE 2023 010"
    assert {"user", "host", "argv", "started"} <= holder.keys()


def test_the_lock_is_free_again_after_release(tmp_path: Path) -> None:
    lock = tmp_path / "bpe.lock"
    with BPELock(lock, purpose="first"):
        pass
    with BPELock(lock, purpose="second"):
        assert json.loads(lock.read_text())["purpose"] == "second"


def test_a_holder_that_died_does_not_block_the_next_run(tmp_path: Path) -> None:
    """flock is released by the kernel when its holder exits, however it exits.
    A leftover file naming a dead pid must not block, unlike a mkdir lock."""
    lock = tmp_path / "bpe.lock"
    code = textwrap.dedent(
        f"""
        import os, sys
        sys.path.insert(0, {str(Path(__file__).resolve().parents[1] / "src")!r})
        from bernese_workflow.bpe_lock import BPELock
        BPELock({str(lock)!r}, purpose="crashed").__enter__()
        os._exit(9)  # no release, no cleanup: as a kill -9 would leave it
        """
    )
    subprocess.run([sys.executable, "-c", code], check=False)
    assert json.loads(lock.read_text())["purpose"] == "crashed"
    with BPELock(lock, purpose="next"):
        assert json.loads(lock.read_text())["purpose"] == "next"


def test_a_record_naming_a_dead_pid_is_called_stale(tmp_path: Path) -> None:
    """The record is only a description; if its pid is gone, say so rather than
    send someone after a process that no longer exists."""
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    lock = tmp_path / "bpe.lock"
    lock.write_text(json.dumps({"pid": gone.pid, "purpose": "old run", "started": "earlier"}))
    msg = BPELock.describe_holder(lock)
    assert "old run" in msg and "stale" in msg


def test_a_live_holder_is_not_called_stale(tmp_path: Path) -> None:
    lock = tmp_path / "bpe.lock"
    with BPELock(lock, purpose="live"):
        msg = BPELock.describe_holder(lock)
    assert "live" in msg and str(os.getpid()) in msg and "stale" not in msg


def test_a_second_lock_in_the_same_process_is_refused_too(tmp_path: Path) -> None:
    """flock belongs to the open file, not the process: a nested run in one
    process (a console that starts a second run) must be refused as well."""
    lock = tmp_path / "bpe.lock"
    with BPELock(lock, purpose="outer"):
        with pytest.raises(BPELockHeld, match="outer"):
            with BPELock(lock, purpose="inner"):
                pass
        assert json.loads(lock.read_text())["purpose"] == "outer"
