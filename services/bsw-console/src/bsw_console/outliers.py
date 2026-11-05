"""Outlier decisions: a person confirms or overrides the statistic's flags.

The design is docs/project_documentation/outlier_review_design.md (#339). In
short: the timeseries package flags epochs automatically; a signed-in person
looks at the plot and records, per epoch, "outlier", "not an outlier", or
clears their decision. Nothing is ever removed from a file. Each decision is
one line appended to <state>/outlier_decisions.jsonl, so the history stays:
the latest line for a (campaign, year, station, epoch) is the current one.

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
from pathlib import Path

from fastapi import HTTPException
from pogf_geodetic_suite.timeseries.crd_pipeline import _extract_session_from_filename

from .settings import Campaign, Settings

DECISIONS = ("outlier", "not_outlier", "cleared")
_EPOCH = re.compile(r"(\d{4})-(\d{3})")
MAX_REASON = 500


def path(s: Settings) -> Path:
    return s.state_dir / "outlier_decisions.jsonl"


def _crd_for(crd_dir: Path, epoch: str) -> Path | None:
    """The daily CRD the epoch came from: the file whose name gives that session."""
    m = _EPOCH.fullmatch(epoch)
    if not m:
        return None
    want = f"{int(m[1]) % 100:02d}{m[2]}"
    for f in sorted(crd_dir.glob("*.CRD")):
        if _extract_session_from_filename(f.name) == want:
            return f
    return None


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


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
    s: Settings, c: Campaign, year: int, station: str, crd_dir: Path, reference: str | None
) -> list[dict]:
    """This station's current decision per epoch (cleared ones dropped), labelled.

    `superseded`: the epoch's CRD file has changed since the decision.
    `other_reference`: the decision was made relative to another reference.
    """
    latest: dict[str, dict] = {}
    count: dict[str, int] = {}
    for row in read_all(s):
        if (row["campaign"], row["year"], row["station"]) != (c.name, year, station):
            continue
        latest[row["epoch"]] = row
        count[row["epoch"]] = count.get(row["epoch"], 0) + 1
    out = []
    for epoch, row in sorted(latest.items()):
        if row["decision"] == "cleared":
            continue
        crd = _crd_for(crd_dir, epoch)
        sha = (row.get("source") or {}).get("sha256")
        out.append(
            {
                **row,
                "history": count[epoch],
                "superseded": crd is None or (sha is not None and _sha256(crd) != sha),
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
    year: int,
    station: str,
    crd_dir: Path,
    user: str,
    body: dict,
) -> dict:
    """Validate and append one decision. The caller has checked who is signed in."""
    epoch = body.get("epoch")
    decision = body.get("decision")
    reason = body.get("reason") or ""
    reference = body.get("reference")
    auto_flag = body.get("auto_flag")
    if not isinstance(epoch, str) or not _EPOCH.fullmatch(epoch):
        raise HTTPException(422, "epoch is a session date, YYYY-DDD")
    if decision not in DECISIONS:
        raise HTTPException(422, f"decision is one of {', '.join(DECISIONS)}")
    if not isinstance(reason, str) or len(reason) > MAX_REASON:
        raise HTTPException(422, f"reason is text of at most {MAX_REASON} characters")
    if not isinstance(reference, str) or not re.fullmatch(r"[A-Z0-9]{4}", reference):
        raise HTTPException(422, "name the reference station the decision was made against")
    if not isinstance(auto_flag, bool):
        raise HTTPException(422, "auto_flag says whether the rule flagged this epoch")
    against = (decision == "outlier" and not auto_flag) or (decision == "not_outlier" and auto_flag)
    if against and not reason.strip():
        raise HTTPException(
            422, "A decision against the automatic flag needs a reason; it is kept with the epoch."
        )
    crd = _crd_for(crd_dir, epoch)
    if crd is None:
        raise HTTPException(404, f"No daily CRD for {epoch} in {crd_dir}")
    row = {
        "v": 1,
        "ts": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "campaign": c.name,
        "year": year,
        "station": station,
        "epoch": epoch,
        "decision": decision,
        "by": user,
        "reason": reason.strip(),
        "reference": reference,
        "auto_flag": auto_flag,
        "rule": {"method": "iqr", "factor": 3.0, "scope": "per_segment", "on": "raw_values"},
        "source": {"crd_dir": str(crd_dir), "file": crd.name, "sha256": _sha256(crd)},
    }
    p = path(s)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
        fcntl.flock(fh, fcntl.LOCK_UN)
    return row
