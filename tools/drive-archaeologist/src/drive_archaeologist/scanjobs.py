"""
Detached scan jobs (DA-005b-2): spawn, registry, liveness, progress.

The TUI never runs a scan in-process — Textual workers die with the app,
and multi-hour NAS scans must survive the TUI closing. Instead the TUI
spawns the real `drive-arch scan` CLI in its own session and records it
in a small state registry; any later TUI instance can re-discover, watch,
pause, or resume it.

Registry: $XDG_STATE_HOME/drive-arch/active_scans.json (~/.local/state).
Progress: the scanner flushes one JSONL record per file, so byte-offset
line counting on the output file IS the progress feed — no IPC.
Liveness: pid + /proc cmdline check, so a recycled pid is never mistaken
for the scan. Jobs are recorded by drive identity (vendor+serial+label),
same rule as the drive picker — never by device letter.

No Textual imports here: the module works from plain CLI/scripts too.
"""

import json
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .tui.devices import DeviceIdentity


def _registry_path() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME", "~/.local/state")
    return Path(state_home).expanduser() / "drive-arch" / "active_scans.json"


@dataclass
class ScanJob:
    pid: int
    argv: list[str]
    root: str
    output_jsonl: str
    console_log: str
    started_at: str
    identity: DeviceIdentity

    def to_dict(self) -> dict:
        return {
            "pid": self.pid,
            "argv": self.argv,
            "root": self.root,
            "output_jsonl": self.output_jsonl,
            "console_log": self.console_log,
            "started_at": self.started_at,
            "identity": {
                "vendor": self.identity.vendor,
                "serial": self.identity.serial,
                "label": self.identity.label,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScanJob":
        ident = data.get("identity") or {}
        return cls(
            pid=int(data["pid"]),
            argv=list(data["argv"]),
            root=data["root"],
            output_jsonl=data["output_jsonl"],
            console_log=data["console_log"],
            started_at=data["started_at"],
            identity=DeviceIdentity(
                vendor=ident.get("vendor"),
                serial=ident.get("serial"),
                label=ident.get("label"),
            ),
        )


def load_jobs() -> list[ScanJob]:
    path = _registry_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [ScanJob.from_dict(entry) for entry in data.get("jobs", [])]
    except (OSError, ValueError, KeyError):
        return []


def _save_jobs(jobs: list[ScanJob]) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"jobs": [j.to_dict() for j in jobs]}, indent=2), encoding="utf-8")


def add_job(job: ScanJob) -> None:
    jobs = [j for j in load_jobs() if j.pid != job.pid]
    jobs.append(job)
    _save_jobs(jobs)


def remove_job(job: ScanJob) -> None:
    _save_jobs([j for j in load_jobs() if j.pid != job.pid])


def prune_jobs() -> list[ScanJob]:
    """Drop registry entries whose process is gone; return the survivors."""
    alive = [j for j in load_jobs() if is_alive(j)]
    _save_jobs(alive)
    return alive


def is_alive(job: ScanJob) -> bool:
    """Is this job's process still running — and still actually our scan?

    A pid alone is not identity: pids get recycled. The /proc cmdline must
    still look like a drive-archaeologist scan before we claim the job lives.
    """
    try:
        os.kill(job.pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    try:
        raw = Path(f"/proc/{job.pid}/cmdline").read_bytes()
    except OSError:
        return False
    args = [a.decode(errors="replace") for a in raw.split(b"\x00") if a]
    # Exact-argument match (substrings would false-positive on e.g. a pytest
    # invocation whose file path mentions drive-archaeologist)
    is_ours = any(
        a == "drive_archaeologist" or a.rsplit("/", 1)[-1] in ("drive-arch", "drive-archaeologist")
        for a in args
    )
    return is_ours and "scan" in args


def count_jsonl_lines(path: Path, offset: int, initial: int = 0) -> tuple[int, int]:
    """Incremental line count: read from byte offset, return (total, new offset).

    The scanner flushes each record, so newline count == files cataloged.
    Callers keep (count, offset) between polls and never re-read old bytes.
    """
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            chunk = f.read()
    except OSError:
        return initial, offset
    return initial + chunk.count(b"\n"), offset + len(chunk)


def spawn_scan(
    *,
    root: Path,
    output: Path,
    identity: DeviceIdentity,
    include_hidden: bool = True,
    max_archive_depth: int = 0,
    excludes: list[str] | None = None,
    force: bool = False,
) -> ScanJob:
    """Spawn `drive-arch scan` detached and register it.

    Always passes --resume so checkpointing is armed from the first file
    (an empty checkpoint still means a fresh scan); --force is only for an
    explicit overwrite decision made in the clobber dialog.
    """
    argv = [
        sys.executable,
        "-m",
        "drive_archaeologist",
        "scan",
        str(root),
        "-o",
        str(output),
        "--resume",
        f"--max-archive-depth={max_archive_depth}",
    ]
    if include_hidden:
        argv.append("--include-hidden")
    if force:
        argv.append("--force")
    for pattern in excludes or []:
        argv += ["--exclude", pattern]

    output.parent.mkdir(parents=True, exist_ok=True)
    console_log = Path(str(output) + ".console.log")
    with open(console_log, "a", encoding="utf-8") as log:
        proc = subprocess.Popen(
            argv,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    job = ScanJob(
        pid=proc.pid,
        argv=argv,
        root=str(root),
        output_jsonl=str(output),
        console_log=str(console_log),
        started_at=datetime.now().isoformat(timespec="seconds"),
        identity=identity,
    )
    add_job(job)
    return job


def pause_job(job: ScanJob) -> None:
    """SIGINT — the scanner's KeyboardInterrupt path saves its checkpoint."""
    os.kill(job.pid, signal.SIGINT)


def cancel_job(job: ScanJob) -> None:
    """SIGTERM — partial output and checkpoint are kept for a later resume."""
    os.kill(job.pid, signal.SIGTERM)


def resume_job(job: ScanJob) -> ScanJob:
    """Re-spawn a paused/dead job. Its argv already carries --resume, so the
    new process picks up from the checkpoint."""
    with open(job.console_log, "a", encoding="utf-8") as log:
        proc = subprocess.Popen(
            job.argv,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    remove_job(job)
    revived = ScanJob(
        pid=proc.pid,
        argv=job.argv,
        root=job.root,
        output_jsonl=job.output_jsonl,
        console_log=job.console_log,
        started_at=datetime.now().isoformat(timespec="seconds"),
        identity=job.identity,
    )
    add_job(revived)
    return revived


def is_complete(job: ScanJob) -> bool:
    """Did the scan finish cleanly (vs crash/kill)? The scanner prints its
    summary banner on every clean completion, including stats-only runs."""
    try:
        return "Scan Complete!" in Path(job.console_log).read_text(errors="replace")
    except OSError:
        return False
