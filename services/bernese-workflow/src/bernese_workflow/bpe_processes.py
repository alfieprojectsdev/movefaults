"""Find BPE processes still running on this machine, read from /proc.

WHY
A BPE driver runs in its own process group (backends._run_bpe_process), so a
timeout can kill all of it. The same property means it survives a worker or a
bernese-run-year that is SIGKILLed, and the BPE lock, an flock, is released
the moment its holder dies. The next run could then start a second BPE beside
the orphan, and a redo's crash recovery would move files under a BPE that is
still writing them.

So the run worker calls ``find`` while holding the BPE lock, before it claims
a job or recovers one. Every legitimate BPE runner takes that lock, so under
it any BPE process found is one nobody is supervising.

WHAT COUNTS AS A BPE PROCESS
  * its environment carries BERNESE_WORKER_REQUEST: the worker sets this for
    the length of each job, and the BPE server and every job shell inherit it
    (backends builds the driver's environment from os.environ), so it marks
    the worker's own BPEs and their programs exactly;
  * its command line runs a BPE script: an interpreter (perl, sh, bash) with
    an argument whose basename is startBPE.pm, RUNBPE.pm, RUNBPE.sh or ends in
    _pcs.pl, or one of those run directly. This catches scripts/ drivers too.
    An editor or grep naming those files is not an interpreter, so it does
    not match.

LIMITS
Only processes this user may read are seen: /proc/<pid>/environ of another
user's process is unreadable and skipped. BPEs run as the processing account,
which is the account the worker runs as.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

WORKER_MARKER = "BERNESE_WORKER_REQUEST"
_SCRIPTS = {"startBPE.pm", "RUNBPE.pm", "RUNBPE.sh"}
_INTERPRETERS = {"perl", "sh", "bash", "dash"}


@dataclass(frozen=True)
class BPEProcess:
    pid: int
    cmdline: str
    campaign: str  # BPE_CAMPAIGN from its environment, "" if absent
    request: str  # the worker request it belongs to, "" if none

    def describe(self) -> str:
        bits = [f"pid {self.pid}"]
        if self.campaign:
            bits.append(f"campaign {self.campaign}")
        if self.request:
            bits.append(f"worker request {self.request}")
        return f"{', '.join(bits)}: {self.cmdline[:120]}"


def _is_bpe_script(arg: str) -> bool:
    base = os.path.basename(arg)
    return base in _SCRIPTS or base.endswith("_pcs.pl")


def _runs_bpe(argv: list[str]) -> bool:
    if not argv:
        return False
    if _is_bpe_script(argv[0]):
        return True
    if os.path.basename(argv[0]) not in _INTERPRETERS:
        return False
    return any(_is_bpe_script(a) for a in argv[1:])


def _environ(raw: bytes) -> dict[str, str]:
    out = {}
    for item in raw.split(b"\0"):
        k, sep, v = item.partition(b"=")
        if sep:
            out[k.decode(errors="replace")] = v.decode(errors="replace")
    return out


def find(proc_root: Path = Path("/proc"), *, exclude: set[int] | None = None) -> list[BPEProcess]:
    """Every BPE process visible under ``proc_root``, except ``exclude`` (default: this one)."""
    skip = {os.getpid()} if exclude is None else exclude
    out = []
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return []
    for d in entries:
        if not d.name.isdigit() or int(d.name) in skip:
            continue
        try:
            argv = [
                a.decode(errors="replace") for a in (d / "cmdline").read_bytes().split(b"\0") if a
            ]
        except OSError:
            continue  # exited, or not ours
        try:
            env = _environ((d / "environ").read_bytes())
        except OSError:
            env = {}
        request = env.get(WORKER_MARKER, "")
        if request or _runs_bpe(argv):
            out.append(
                BPEProcess(int(d.name), " ".join(argv), env.get("BPE_CAMPAIGN", ""), request)
            )
    return sorted(out, key=lambda p: p.pid)
