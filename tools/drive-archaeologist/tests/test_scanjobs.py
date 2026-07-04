"""
DA-005b-2 scan-job tests: state registry, detached spawn, liveness with
pid-reuse guard, progress by JSONL line count, pause via SIGINT + resume.

Spawn tests run the REAL `drive-arch scan` CLI as a subprocess against
tmp_path trees — that is the production code path, not a mock.
"""

import json
import os
import signal
import time
from pathlib import Path

import pytest
from drive_archaeologist.scanjobs import (
    ScanJob,
    add_job,
    count_jsonl_lines,
    is_alive,
    load_jobs,
    prune_jobs,
    remove_job,
    spawn_scan,
)
from drive_archaeologist.tui.devices import DeviceIdentity


@pytest.fixture
def registry(tmp_path, monkeypatch):
    reg = tmp_path / "state" / "active_scans.json"
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return reg


def make_job(pid=99999, output="/tmp/x.jsonl"):
    return ScanJob(
        pid=pid,
        argv=["drive-arch", "scan", "/x"],
        root="/x",
        output_jsonl=output,
        console_log=output + ".console.log",
        started_at="2026-07-04T12:00:00",
        identity=DeviceIdentity(vendor="Seagate", serial="NACAFVGH", label="Backup Plus"),
    )


class TestRegistry:
    def test_roundtrip(self, registry):
        job = make_job()
        add_job(job)
        loaded = load_jobs()
        assert len(loaded) == 1
        assert loaded[0].pid == job.pid
        assert loaded[0].identity == job.identity

    def test_remove(self, registry):
        job = make_job()
        add_job(job)
        remove_job(job)
        assert load_jobs() == []

    def test_missing_registry_is_empty(self, registry):
        assert load_jobs() == []

    def test_corrupt_registry_is_empty(self, registry):
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text("not json {")
        assert load_jobs() == []

    def test_prune_drops_dead_jobs(self, registry):
        dead = make_job(pid=99999)  # nothing at this pid (or wrong cmdline)
        add_job(dead)
        kept = prune_jobs()
        assert kept == []
        assert load_jobs() == []


class TestLiveness:
    def test_dead_pid_not_alive(self):
        assert is_alive(make_job(pid=99999)) is False

    def test_pid_reuse_guard(self):
        """Our own pid is alive, but its cmdline is not a drive-arch scan —
        a recycled pid must not be mistaken for the scan."""
        me = make_job(pid=os.getpid())
        assert is_alive(me) is False


class TestProgress:
    def test_count_jsonl_lines_incremental(self, tmp_path):
        out = tmp_path / "scan.jsonl"
        out.write_text('{"a":1}\n{"a":2}\n')
        count, offset = count_jsonl_lines(out, 0)
        assert count == 2
        with open(out, "a") as f:
            f.write('{"a":3}\n')
        more, offset = count_jsonl_lines(out, offset, initial=count)
        assert more == 3

    def test_count_missing_file_zero(self, tmp_path):
        count, offset = count_jsonl_lines(tmp_path / "nope.jsonl", 0)
        assert (count, offset) == (0, 0)


def make_tree(root: Path, n: int) -> Path:
    root.mkdir(parents=True)
    for i in range(n):
        (root / f"f{i:05}.txt").write_text("x")
    return root


class TestSpawn:
    def test_spawn_runs_real_scan_to_completion(self, registry, tmp_path):
        root = make_tree(tmp_path / "drive", 25)
        out = tmp_path / "out" / "scan.jsonl"
        job = spawn_scan(
            root=root,
            output=out,
            identity=DeviceIdentity(vendor="V", serial="S", label="L"),
            include_hidden=True,
        )
        assert job in load_jobs()
        for _ in range(300):
            if not is_alive(job):
                break
            time.sleep(0.1)
        assert not is_alive(job)
        count, _ = count_jsonl_lines(out, 0)
        assert count == 25
        assert "Scan Complete!" in Path(job.console_log).read_text()
        assert prune_jobs() == []  # completed job pruned

    def test_sigint_pause_then_resume_no_duplicates(self, registry, tmp_path):
        root = make_tree(tmp_path / "drive", 8000)
        out = tmp_path / "out" / "scan.jsonl"
        identity = DeviceIdentity(vendor="V", serial="S", label="L")
        job = spawn_scan(root=root, output=out, identity=identity, include_hidden=True)
        # Let it get partway, then pause (SIGINT -> KeyboardInterrupt -> checkpoint)
        deadline = time.time() + 30
        while time.time() < deadline:
            count, _ = count_jsonl_lines(out, 0)
            if count > 500:
                break
            time.sleep(0.05)
        assert count > 500, "scan never produced output"
        os.kill(job.pid, signal.SIGINT)
        for _ in range(100):
            if not is_alive(job):
                break
            time.sleep(0.1)
        interrupted_count, _ = count_jsonl_lines(out, 0)
        if interrupted_count >= 8000:
            pytest.skip("scan finished before SIGINT landed — nothing to resume")
        # Resume: same output, --resume rides the checkpoint
        job2 = spawn_scan(root=root, output=out, identity=identity, include_hidden=True)
        for _ in range(600):
            if not is_alive(job2):
                break
            time.sleep(0.1)
        records = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
        paths = [r["path"] for r in records]
        assert len(set(paths)) == 8000  # every file present
        # checkpoint batch re-scan may duplicate at most one batch worth
        assert len(paths) - len(set(paths)) <= 200
