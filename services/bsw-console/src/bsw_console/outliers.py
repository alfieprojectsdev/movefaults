"""Outlier decisions: a person confirms or overrides the statistic's flags.

The design is docs/project_documentation/outlier_review_design.md (#339). In
short: the timeseries package flags epochs automatically; a signed-in person
looks at the plot and records, per epoch, "outlier", "not an outlier", or
clears their decision. Nothing is ever removed from a file. Each decision is
one line appended to <state>/outlier_decisions.jsonl, so the history stays:
the latest line for a (campaign, station, epoch) is the current one. An epoch
names its own year, so a series spanning years needs nothing more.

Every line carries what it was made against, so a decision is never silently
reused on something else:
- the reference station: an apparent outlier can be the reference's bad day,
  so a decision made relative to one reference is labelled when another is
  chosen;
- the CRD file's sha256: when a day is reprocessed (PHREF 2025 was, on
  2026-11-04), the decision is labelled "made on a superseded solution".

What the decisions change is only the side-by-side fit the page shows as NOT
published. Whether confirmed outliers leave the published fit is SETTLED.md
section 6, still open.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import json
import os
import re
from collections.abc import Callable
from pathlib import Path

from fastapi import HTTPException
from pogf_geodetic_suite.timeseries.crd_pipeline import _extract_session_from_filename

from .settings import Campaign, Settings

DECISIONS = ("outlier", "not_outlier", "cleared")
_EPOCH = re.compile(r"(\d{4})-(\d{3})")
MAX_REASON = 500


def path(s: Settings) -> Path:
    return s.state_dir / "outlier_decisions.jsonl"


def _crds_for(crd_dirs: list[Path], epoch: str) -> list[Path]:
    """Every daily CRD whose name gives that session (F1_ and FIN_ can both be
    present for one day; the series then carries both, so both are hashed).
    Looks in all the campaign's folders, the same files the series reads."""
    m = _EPOCH.fullmatch(epoch)
    if not m:
        return []
    want = f"{int(m[1]) % 100:02d}{m[2]}"
    return [
        f
        for d in crd_dirs
        for f in sorted(d.glob("*.CRD"))
        if _extract_session_from_filename(f.name) == want
    ]


def _sha256(files: list[Path]) -> str:
    """One hash over the day's file(s), by name and content, in name order."""
    h = hashlib.sha256()
    for f in files:
        h.update(f.name.encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


def read_all(s: Settings) -> list[dict]:
    """Every decision line, oldest first. A malformed line is skipped, not fatal."""
    p = path(s)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if (
            isinstance(row, dict)
            and {"campaign", "year", "station", "epoch", "decision"} <= row.keys()
        ):
            out.append(row)
    return out


def current(
    s: Settings, c: Campaign, station: str, crd_dirs: list[Path], reference: str | None
) -> list[dict]:
    """This station's current decision per epoch (cleared ones dropped), labelled.

    `superseded`: the epoch's CRD file has changed since the decision.
    `other_reference`: the decision was made relative to another reference.
    """
    latest: dict[str, dict] = {}
    count: dict[str, int] = {}
    for row in read_all(s):
        if (row["campaign"], row["station"]) != (c.name, station):
            continue
        latest[row["epoch"]] = row
        count[row["epoch"]] = count.get(row["epoch"], 0) + 1
    out = []
    for epoch, row in sorted(latest.items()):
        if row["decision"] == "cleared":
            continue
        crds = _crds_for(crd_dirs, epoch)
        sha = (row.get("source") or {}).get("sha256")
        out.append(
            {
                **row,
                "history": count[epoch],
                "superseded": not crds or (sha is not None and _sha256(crds) != sha),
                "other_reference": row.get("reference") != reference,
            }
        )
    return out


def excluded_sessions(decisions: list[dict]) -> list[str]:
    """Epochs to leave out of the side-by-side fit: confirmed outliers made
    relative to the reference shown, on the solution shown."""
    return [
        d["epoch"]
        for d in decisions
        if d["decision"] == "outlier" and not d["superseded"] and not d["other_reference"]
    ]


def record(
    s: Settings,
    c: Campaign,
    station: str,
    crd_dirs: list[Path],
    user: str,
    body: dict,
    flag_of: Callable[[str, str], bool],
) -> dict:
    """Validate and append one decision. The caller has checked who is signed in.

    `flag_of(epoch, reference)` is the rule's own flag for that epoch, computed
    by the server: the browser's `auto_flag` is not trusted, because the reason
    rule depends on it. It raises 404 when the station has no such epoch.
    """
    epoch = body.get("epoch")
    decision = body.get("decision")
    reason = body.get("reason") or ""
    reference = body.get("reference")
    if not isinstance(epoch, str) or not _EPOCH.fullmatch(epoch):
        raise HTTPException(422, "epoch is a session date, YYYY-DDD")
    if decision not in DECISIONS:
        raise HTTPException(422, f"decision is one of {', '.join(DECISIONS)}")
    if not isinstance(reason, str) or len(reason) > MAX_REASON:
        raise HTTPException(422, f"reason is text of at most {MAX_REASON} characters")
    if not isinstance(reference, str) or not re.fullmatch(r"[A-Z0-9]{4}", reference):
        raise HTTPException(422, "name the reference station the decision was made against")
    crds = _crds_for(crd_dirs, epoch)
    if not crds:
        raise HTTPException(404, f"No daily CRD for {epoch} in {c.name}")
    auto_flag = flag_of(epoch, reference)
    against = (decision == "outlier" and not auto_flag) or (decision == "not_outlier" and auto_flag)
    if against and not reason.strip():
        raise HTTPException(
            422, "A decision against the automatic flag needs a reason; it is kept with the epoch."
        )
    row = {
        "v": 1,
        "ts": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "campaign": c.name,
        "year": int(epoch[:4]),
        "station": station,
        "epoch": epoch,
        "decision": decision,
        "by": user,
        "reason": reason.strip(),
        "reference": reference,
        "auto_flag": auto_flag,
        "rule": {"method": "iqr", "factor": 3.0, "scope": "per_segment", "on": "raw_values"},
        "source": {
            "crd_dir": str(crds[0].parent),
            "file": crds[0].name,
            "files": [f.name for f in crds],
            "sha256": _sha256(crds),
        },
    }
    p = path(s)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        # A write cut short (power loss) leaves a line with no newline; start a
        # new line, so this decision is not glued onto it and lost with it.
        if fh.tell() > 0:
            with open(p, "rb") as rd:
                rd.seek(-1, os.SEEK_END)
                if rd.read(1) != b"\n":
                    fh.write("\n")
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
        fcntl.flock(fh, fcntl.LOCK_UN)
    return row
