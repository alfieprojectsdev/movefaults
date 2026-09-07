#!/usr/bin/env python3
"""Find documentation that refers to things which no longer exist.

WHY THIS EXISTS
This repository's documentation is its succession plan, and it has a recorded
history of going stale: `CLAUDE.md` carries a "Corrections to earlier versions"
block, and `SETTLED.md` §5 exists solely for "superseded claims still in
circulation". Both were written after a session wasted time re-deriving
something a stale doc had asserted.

Prose claims cannot be checked mechanically. **File references can.** A
document citing `scripts/foo.py` when no such file exists is stale by
construction, and that is the cheapest reliable staleness signal available.

WHAT IT DOES NOT DO
It does not judge whether a statement is true. A path that exists proves
nothing about the sentence around it.

HISTORICAL DOCUMENTS ARE NOT STALE
A session log recording that a file existed in August is correct, even after
the file is deleted. Dated records — session logs, change requests, handovers —
are reported separately and should not be "fixed". Confusing the two would
rewrite history to match the present, which is the opposite of the point.

Usage:
    scripts/audit_doc_references.py
    scripts/audit_doc_references.py --include-historical
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# A dated record of what was true then, not a claim about now.
HISTORICAL = re.compile(
    r"(SESSION_LOG|CR-\d{8}|HANDOVER|_20\d{6}|session_log|RESUME_NEXT)", re.I)

# Backticked paths that look like repo files. Deliberately narrow: a path must
# have a directory separator or a known source extension, so prose like
# `main` or `--flag` is not mistaken for a file.
PATHISH = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./\-]*"
                     r"(?:/[A-Za-z0-9_.\-]+|\.(?:py|sh|md|csv|yml|yaml|toml|pl|PCF|INP))"
                     r"[A-Za-z0-9_./\-]*)`")

# Referenced but deliberately outside the repo. Bernese lives under $D/$P/$S
# and its own file types are not repo files; flagging them made the first run
# 90% noise, which is the same failure this audit exists to catch.
EXTERNAL = re.compile(r"^(/|~|\$|\.\./|https?:)")
# Claude Code's memory lives in ~/.claude/projects/<key>/memory/, outside the
# repo by design. A doc citing memory/foo.md is not citing a missing file.
OUTSIDE_REPO = re.compile(r"^(memory|\.claude|handover)/", re.I)
BERNESE = re.compile(
    r"^(DATAPOOL|CAMPAIGN\d*|SAVEDISK|GPSDATA|GPSUSER|BERN\d+|REF\d+|OPT|PAN|PCF)/"
    r"|\.(PCF|INP|CRD|STA|BLQ|ATL|ABB|CLU|VEL|SNX|NQ0|PRC|SES|SAT|CRX|SUB|NUT|PCV)$",
    re.I)
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__"}


def tracked_files() -> set[str]:
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True)
    return set(out.stdout.split())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--include-historical", action="store_true")
    ap.add_argument("--root", type=Path, default=Path("."))
    args = ap.parse_args()

    tracked = tracked_files()
    # A doc saying "see `backends.py`" is using shorthand for a file that does
    # exist. Resolving only doc-relative and repo-root paths called 31 such
    # references in CLAUDE.md dead when none were.
    basenames = {Path(f).name for f in tracked}
    docs = [Path(f) for f in tracked if f.endswith(".md")]
    print(f"  markdown files tracked: {len(docs)}")

    live_bad: dict[str, list[tuple[int, str]]] = {}
    hist_bad: dict[str, list[tuple[int, str]]] = {}
    checked = 0

    for d in docs:
        try:
            lines = d.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        bad = []
        for i, line in enumerate(lines, 1):
            for m in PATHISH.finditer(line):
                ref = m.group(1)
                if (EXTERNAL.match(ref) or BERNESE.match(ref)
                        or OUTSIDE_REPO.match(ref)
                        or any(p in SKIP_DIRS for p in ref.split("/"))):
                    continue
                checked += 1
                # Resolve relative to the doc, then to the repo root.
                if ((d.parent / ref).exists() or Path(ref).exists()
                        or ref in tracked or Path(ref).name in basenames):
                    continue
                bad.append((i, ref))
        if bad:
            (hist_bad if HISTORICAL.search(str(d)) else live_bad)[str(d)] = bad

    print(f"  path-like references checked: {checked:,}")
    print(f"\n  LIVE documents with dead references: {len(live_bad)}")
    for f, refs in sorted(live_bad.items(), key=lambda kv: -len(kv[1])):
        print(f"    {f}  ({len(refs)})")
        for ln, r in refs[:6]:
            print(f"       :{ln}  {r}")
        if len(refs) > 6:
            print(f"       … {len(refs) - 6} more")

    print(f"\n  HISTORICAL documents with dead references: {len(hist_bad)}"
          f"  ({sum(len(v) for v in hist_bad.values())} refs)")
    print("    These are dated records. A reference that was correct when written\n"
          "    stays correct; do not 'fix' them to match the present.")
    if args.include_historical:
        for f, refs in sorted(hist_bad.items(), key=lambda kv: -len(kv[1])):
            print(f"    {f}  ({len(refs)})")

    return 1 if live_bad else 0


if __name__ == "__main__":
    sys.exit(main())
