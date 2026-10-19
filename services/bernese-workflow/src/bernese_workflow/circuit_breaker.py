"""
Decide, after each failed day, whether a multi-day run may go on.

Step 3 of the decision layer in
``docs/project_documentation/bpe_orchestration_design.md``. The scanner names a
failure (``bpe_scanner``), the knowledge base says what it is
(``bpe_knowledge``), and this decides whether the next day is worth running.
It encodes one distinction: a failure that belongs to one day's data is data;
the same failure on day after day is configuration, and running more days only
repeats it. On 29 August 2026 ADDNEQ2's MAXPAR failed 24 days in nine hours.

The rules, in order:

1. **Unknown halts at once.** A failed step with no ``***`` message, an error
   with no row in the knowledge base, or a failed day whose BPE left no failed
   step at all (a timeout, a backend exception, success without a FIN). There
   is no default remedy, so there is nothing to gain from another day.
2. **``scope: configuration`` halts at once.** The setup is wrong and every day
   will fail the same way.
3. **``scope: session`` is counted.** The day is reported and the run goes on,
   until ``k`` consecutive failed days share one signature. A success, or a
   different signature, restarts the count. Banked (skipped) days are not
   attempts and do not touch it.

``k`` = 3 was approved on 2026-10-15.

Finding the failed step
-----------------------

BPE writes each step's output to the campaign's ``BPE/`` directory as
``<task><yy><session>_<PID>_<sub>.PRT`` and ``.LOG``, for example
``RP252000_322_017.PRT``. The task id is two letters set by the driver script
(``RS`` in stock ``rnx2snx_pcs.pl``, ``RP`` in ours), so it is not matched.
Files from an earlier attempt at the same day stay in the directory, so only
files modified since the attempt started count. Of the failed steps, the one
with the lowest PID and sub-number is the cause: later failures are usually
its consequence, and parallel sub-jobs of one script tend to fail alike.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from bernese_workflow.bpe_knowledge import Entry, KnowledgeBase, explain
from bernese_workflow.bpe_scanner import StepReport, scan_file

K_DEFAULT = 3

# Filesystem mtimes can sit slightly behind time.time(); a BPE day takes minutes,
# so a second of slack cannot let an earlier attempt's file in.
_MTIME_SLACK = 1.0


@dataclass(frozen=True)
class Diagnosis:
    """What one failed day's BPE output says, and what the knowledge base adds."""

    step: Path | None  # the failed step's file, None when no step failed
    report: StepReport | None
    entry: Entry | None

    @property
    def key(self) -> tuple[str, str] | None:
        """The signature the breaker counts, matched as the knowledge base matches."""
        if self.report is None or self.report.cause is None:
            return None
        cause = self.report.cause
        return (cause.emitter.lower(), cause.kind)

    @property
    def label(self) -> str:
        if self.report is None:
            return "no failed BPE step"
        cause = self.report.cause
        if cause is None:
            return f"{self.report.failed_program} failed with no *** message"
        return f"{cause.emitter}: {cause.kind}"

    def explanation(self, kb: KnowledgeBase) -> str:
        if self.step is None or self.report is None:
            return (
                "No BPE step reported a failure. UNKNOWN: read the BPE output and the driver's log."
            )
        return f"{self.step.name}\n{explain(self.report, kb)}"


def _step_order(path: Path) -> tuple[int, int, str]:
    m = re.search(r"_(\d{3})_(\d{3})$", path.stem)
    return (int(m[1]), int(m[2]), path.name) if m else (999, 999, path.name)


def diagnose_day(
    bpe_dir: Path, year: int, session: str, since: float, kb: KnowledgeBase
) -> Diagnosis:
    """Find the failed step this attempt left in ``bpe_dir`` and look it up.

    ``since`` is the attempt's start, as ``time.time()``.
    """
    pattern = f"*{year % 100:02d}{session}_[0-9][0-9][0-9]_[0-9][0-9][0-9]"
    stems: dict[str, list[Path]] = {}
    for suffix in (".PRT", ".LOG"):
        for p in bpe_dir.glob(pattern + suffix):
            if p.stat().st_mtime >= since - _MTIME_SLACK:
                stems.setdefault(p.stem, []).append(p)

    for stem in sorted(stems, key=lambda s: _step_order(Path(s))):
        # PRT before LOG: the PRT's ERR line bounds which message is the cause.
        files = sorted(stems[stem], key=lambda p: p.suffix != ".PRT")
        reports = [(p, scan_file(p)) for p in files]
        failed = [(p, r) for p, r in reports if r.failed]
        if not failed:
            continue
        path, report = next(((p, r) for p, r in failed if r.cause is not None), failed[0])
        entry = kb.lookup(report.cause) if report.cause is not None else None
        return Diagnosis(path, report, entry)
    return Diagnosis(None, None, None)


class CircuitBreaker:
    """Counts failed days by signature. ``failure`` returns why to halt, or None."""

    def __init__(self, k: int = K_DEFAULT) -> None:
        if k < 1:
            raise ValueError(f"k must be at least 1, not {k}")
        self.k = k
        self._key: tuple[str, str] | None = None
        self._count = 0

    def success(self) -> None:
        self._key, self._count = None, 0

    def failure(self, diagnosis: Diagnosis) -> str | None:
        key = diagnosis.key
        if key is None or diagnosis.entry is None:
            self.success()
            return f"unknown failure ({diagnosis.label}); no remedy on file"
        if diagnosis.entry.scope == "configuration":
            self.success()
            return f"configuration error ({diagnosis.label}); every day would fail the same way"
        self._count = self._count + 1 if key == self._key else 1
        self._key = key
        if self._count >= self.k:
            return f"{self._count} consecutive days failed with {diagnosis.label}"
        return None
