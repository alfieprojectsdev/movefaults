"""
USER.CPU maxjobs sizing for the BPE (RH-006 / readiness task L).

The BPE runs its parallel sub-solves (clustered GPSEST etc.) as independent OS
processes, one per free slot in ``USER.CPU``'s ``maxjobs`` for a CPU. Each is a
dense normal-equation inversion — **FPU-bound**, so hyperthreads don't help:
maxjobs should track *physical cores*, not logical CPUs, and be capped by RAM so
concurrent inversions don't thrash (each large-network sub-solve wants ~GBs).

This is the ``USER.CPU`` half of the 502 GPSCLU_P bottleneck fix; the other half
(final-solution clustering, ``V_CLUFIN``) is exposed via ``PCFContext`` but its
optimal value is empirical and needs the R740 (BRN-001) to tune — see the ticket.
"""
from __future__ import annotations

import re


def compute_maxjobs(
    physical_cores: int,
    *,
    ram_gb: float | None = None,
    ram_per_job_gb: float = 2.0,
    reserve_cores: int = 0,
) -> int:
    """Return a safe BPE ``maxjobs`` for one host.

    Base = physical cores minus *reserve_cores* (leave headroom for the BPE server
    / OS), floored at 1. When *ram_gb* is given, additionally cap at
    ``floor(ram_gb / ram_per_job_gb)`` so concurrent inversions don't exhaust RAM.

    Use physical cores, NOT logical CPUs — the sub-solves are FPU-bound and gain
    nothing (often lose) from hyperthreads sharing an FPU.
    """
    if physical_cores < 1:
        raise ValueError(f"physical_cores must be >= 1, got {physical_cores}")
    if ram_per_job_gb <= 0:
        raise ValueError(f"ram_per_job_gb must be > 0, got {ram_per_job_gb}")

    jobs = max(1, physical_cores - reserve_cores)
    if ram_gb is not None:
        ram_cap = max(1, int(ram_gb // ram_per_job_gb))
        jobs = min(jobs, ram_cap)
    return jobs


# The localhost CPU row in USER.CPU:
#   "localhost" "<command>" "<speed>" "<maxjobs>" "<jobs>" "<wait>"
# Group 2 is the maxjobs integer. The command field uses single quotes internally,
# so "[^"]*" safely spans it. Anchored per-line; never matches MSG_/comment lines.
_CPU_MAXJOBS_RE = re.compile(
    r'^(\s*"localhost"\s+"[^"]*"\s+"[^"]*"\s+")(\d+)(")', re.MULTILINE
)


def set_user_cpu_maxjobs(text: str, maxjobs: int) -> tuple[str, bool]:
    """Rewrite the ``localhost`` CPU's ``maxjobs`` field in USER.CPU content.

    Leaves the command, speed, and the jobs/wait counters untouched. Returns
    ``(new_text, changed)``; *changed* is False if no localhost CPU row is present.
    """
    if maxjobs < 1:
        raise ValueError(f"maxjobs must be >= 1, got {maxjobs}")
    new_text, n = _CPU_MAXJOBS_RE.subn(
        lambda m: f"{m.group(1)}{maxjobs}{m.group(3)}", text
    )
    return new_text, n > 0
