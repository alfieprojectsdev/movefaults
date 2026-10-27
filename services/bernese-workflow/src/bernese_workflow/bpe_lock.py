"""One BPE run at a time on a machine, enforced rather than remembered.

WHY
Two BPE runs on one machine fight over the CPU file, the BPE server and, unless
every session has a private campaign, the campaign itself. The scripts/ drivers
each kept their own mkdir lock (~/.run_luzon_month.lock, ~/.run_phref_year.lock),
which stops a second copy of the SAME script and nothing else, and a mkdir lock
left by a killed run blocks every later run until someone removes it by hand.

HOW
An fcntl.flock on one file per machine. The kernel releases it when the holder
exits, however it exits, so a crash cannot leave a lock that blocks the next
run. The file also records who holds it (pid, user, host, argv, purpose, start
time), so a refused run can say who to ask. That record is only a description:
the flock is the lock. A record naming a pid that no longer exists is therefore
just stale text, and is reported as such rather than trusted.

The path is BPE_LOCK in the environment, else
~/.local/state/bernese-workflow/bpe.lock. Every run on the machine has to agree
on the path for the lock to mean anything, which is why it is not a CLI option.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import getpass
import json
import os
import socket
import sys
from pathlib import Path
from typing import IO

DEFAULT_PATH = Path.home() / ".local/state/bernese-workflow/bpe.lock"


def default_path() -> Path:
    return Path(os.environ["BPE_LOCK"]) if os.environ.get("BPE_LOCK") else DEFAULT_PATH


class BPELockHeld(RuntimeError):
    """Another run holds the machine's BPE lock. The message says who."""


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # it exists; it is someone else's
    return True


class BPELock:
    """Context manager: hold the machine's BPE lock for the duration of a run."""

    def __init__(self, path: Path | str | None = None, *, purpose: str = "") -> None:
        self.path = Path(path) if path is not None else default_path()
        self.purpose = purpose
        self._fh: IO[str] | None = None

    def __enter__(self) -> BPELock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # "a+", not "w": a contender must not truncate the record it is about to
        # report. The file is rewritten only once the lock is ours.
        fh = open(self.path, "a+")  # noqa: SIM115 -- held for the life of the lock
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fh.close()
            raise BPELockHeld(
                f"another BPE run holds {self.path}: {self.describe_holder(self.path)}"
            ) from None
        fh.seek(0)
        fh.truncate()
        json.dump(
            {
                "pid": os.getpid(),
                "user": getpass.getuser(),
                "host": socket.gethostname(),
                "argv": sys.argv,
                "purpose": self.purpose,
                "started": dt.datetime.now().isoformat(timespec="seconds"),
            },
            fh,
        )
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
        self._fh = fh
        return self

    def __exit__(self, *exc: object) -> None:
        if self._fh is not None:
            # The record is left in place: it is history, and the next holder
            # overwrites it. Closing releases the flock.
            self._fh.close()
            self._fh = None

    @staticmethod
    def describe_holder(path: Path | str) -> str:
        """Who the lock file says holds it, flagged if that pid is gone."""
        try:
            rec = json.loads(Path(path).read_text() or "{}")
        except (OSError, json.JSONDecodeError):
            return "holder unknown (the lock file has no readable record)"
        if not rec:
            return "holder unknown (the lock file is empty)"
        pid = rec.get("pid")
        who = (
            f"pid {pid} ({rec.get('user', '?')}@{rec.get('host', '?')}), "
            f"since {rec.get('started', '?')}, {rec.get('purpose') or 'no purpose given'}"
        )
        if isinstance(pid, int) and not _pid_alive(pid):
            who += "; that pid is no longer running, so this record is stale"
        return who
