"""The Plan screen: what RUNBPE 1 and 2 ask for, checked before anything runs.

The day selection, the reference-station check and MAXPAR come from
bernese_workflow.run_plan.plan_from_env, the function `bernese-run-year --plan`
prints, so the plan a person reads here is the plan the service would run.
What this module adds is what the CLI does not have yet: the PCF as groups of
steps, a check of the skips a person chooses, and the products per day.
Saving a plan writes one JSON file under the console's state directory; it is
the only thing this module writes.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import threading
import uuid
from pathlib import Path

from bernese_workflow import run_plan
from bernese_workflow.product_update import PRODUCTS

from .settings import Campaign, Settings
from .status import GROUPS, _group, day_info, day_results, lock_status, year_dir

_ROW = re.compile(r"^(\d{3})\s+(\S+)\s+(\S+)\s*(.*)$")
_WAIT = re.compile(r"WAIT\s*=\s*([\d\s]+)")
_TABLE_END = re.compile(r"^(PID\s+USER\b|VARIABLE\b)")

# plan_from_env reads $U, $D and $S from the process environment.
_ENV_LOCK = threading.Lock()

RNXGRA_PRESETS = {
    "continuous": "Continuous · min 200 obs, max 10 bad epochs, 3 obs per bad epoch",
    "campaign": "Campaign survey · min 100 obs, max 70 bad epochs, 3 obs per bad epoch",
}

def pcf_steps(pcf_text: str) -> list[dict]:
    """The PCF's process table: PID, script, option dir and what each WAITs for."""
    steps = []
    started = False
    for raw in pcf_text.splitlines():
        line = raw.rstrip()
        if line.startswith("PID ") and "SCRIPT" in line:
            started = True
            continue
        if not started or line.startswith("#") or not line.strip():
            continue
        if _TABLE_END.match(line):
            break
        m = _ROW.match(line)
        if not m:
            continue
        w = _WAIT.search(m[4])
        steps.append(
            {
                "pid": int(m[1]),
                "script": m[2],
                "opt": m[3],
                "waits": [int(x) for x in w[1].split()] if w else [],
                "group": _group(int(m[1])),
            }
        )
    return steps


def step_groups(steps: list[dict]) -> list[dict]:
    out = []
    for i, (key, name) in enumerate(GROUPS):
        mine = [st for st in steps if st["group"] == i]
        if mine:
            out.append(
                {
                    "index": i,
                    "key": key,
                    "name": name,
                    "pids": [f"{st['pid']:03d} {st['script']}" for st in mine],
                }
            )
    return out


def dangling_from_skips(steps: list[dict], skipped: set[int]) -> list[str]:
    """Steps that would run while WAITing on a skipped step.

    Groups before the first one left on are "start with", as in RUNBPE 2: the
    BPE treats everything before the start as done. A group switched off after
    the start is a skip, and a running step that waits on one of its PIDs waits
    for ever.
    """
    groups_on = sorted({st["group"] for st in steps} - skipped)
    if not groups_on:
        return ["every group is skipped: nothing would run"]
    start = groups_on[0]
    skipped_pids = {st["pid"] for st in steps if st["group"] in skipped and st["group"] > start}
    out = []
    for st in steps:
        if st["group"] in skipped or st["group"] < start:
            continue
        for w in st["waits"]:
            if w in skipped_pids:
                out.append(f"{st['pid']:03d} {st['script']} waits on {w:03d}, which is skipped")
    return out


def products(s: Settings, year: int, doys: list[int]) -> dict:
    missing: dict[str, list[int]] = {}
    for label, folder, pattern in PRODUCTS:
        for doy in doys:
            if not (s.datapool / folder / pattern.format(y=year, d=f"{doy:03d}")).is_file():
                missing.setdefault(label, []).append(doy)
    return {
        "checked": len(doys),
        "missing": missing,
        "source": "DATAPOOL (fetched from the SWITCH S3 mirror)",
    }


def build(
    s: Settings,
    c: Campaign,
    year: int,
    doy_from: int,
    doy_to: int,
    *,
    pcf: str | None = None,
    skipped: set[int] | None = None,
    rnxgra: str = "continuous",
) -> dict:
    pcf = pcf or c.pcf
    skipped = skipped or set()
    with _ENV_LOCK:
        saved = {k: os.environ.get(k) for k in ("U", "D", "S")}
        os.environ.update({k: v for k, v in s.env.items() if k in ("U", "D", "S")})
        try:
            planned = run_plan.plan_from_env(
                campaign=c.name, year=year, pcf=pcf, doy_from=doy_from, doy_to=doy_to
            )
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    p = planned.plan
    steps = pcf_steps(planned.pcf_text)
    dangling = dangling_from_skips(steps, skipped)
    prod = products(s, year, p.todo)
    checks = []
    short = [e for e in p.excluded if e.reason == "short"]
    solved = [e for e in p.excluded if e.reason == "solved"]
    checks.append(
        {
            "level": "info",
            "title": f"{len(p.todo)} of {doy_to - doy_from + 1} days will run; {len(short)} excluded, {len(solved)} already solved",
            "detail": "; ".join(f"DOY {e.doy:03d} ({e.detail})" for e in short)
            or "No day is short of reference stations.",
        }
    )
    busiest = p.busiest
    checks.append(
        {
            "level": "ok" if all(v for v in p.maxpar.values()) else "bad",
            "title": "MAXPAR in the ADDNEQ2 option directories",
            "detail": ", ".join(
                f"{k} {v if v is not None else 'not found'}" for k, v in p.maxpar.items()
            )
            + (
                f". Busiest day DOY {busiest:03d}, {p.station_counts.get(busiest, 0)} stations with data."
                if busiest
                else ""
            ),
        }
    )
    pcf_problems = run_plan.check_pcf(planned.pcf_text)
    checks.append(
        {
            "level": "bad" if dangling or pcf_problems else "ok",
            "title": "Dangling WAIT in the PCF"
            if dangling or pcf_problems
            else "No dangling WAIT or NEXTJOB",
            "detail": "; ".join(dangling + pcf_problems)
            or "Every script that runs has the script it waits for.",
        }
    )
    missing = prod["missing"]
    checks.append(
        {
            "level": "bad" if missing else "ok",
            "title": "Products present for every day" if not missing else "Products missing",
            "detail": "; ".join(
                f"{k}: DOY " + ", ".join(f"{d:03d}" for d in v[:10]) + (" …" if len(v) > 10 else "")
                for k, v in missing.items()
            )
            or f"CODE final orbits, clocks, ERP, OSB and ionosphere for {prod['checked']} of {prod['checked']} days.",
        }
    )
    other = [x for x in p.problems if x not in pcf_problems]
    if other:
        checks.append(
            {"level": "bad", "title": "Problems the service found", "detail": "; ".join(other)}
        )
    checks.append(
        {
            "level": "info",
            "title": "Preflight not run yet",
            "detail": f"The hardest day (DOY {busiest:03d}) is run first, so a configuration error shows up before the whole range."
            if busiest
            else "No day to preflight.",
        }
    )
    blocking = [x for x in checks if x["level"] == "bad"]
    why = []
    if blocking:
        why.append("fix the checks marked above")
    return {
        "campaign": c.name,
        "year": year,
        "pcf": pcf,
        "from": day_info(year, doy_from),
        "to": day_info(year, doy_to),
        "todo": p.todo,
        "blocks": p.blocks,
        "busiest": busiest,
        "excluded": [{"doy": e.doy, "reason": e.reason, "detail": e.detail} for e in p.excluded],
        "maxpar": p.maxpar,
        "label": planned.label,
        "sources": planned.sources,
        "groups": step_groups(steps),
        "skipped": sorted(skipped),
        "rnxgra": rnxgra,
        "rnxgra_presets": RNXGRA_PRESETS,
        "checks": checks,
        "can_start": not why,
        "start_blocked_because": why,
        "pcfs": campaign_pcfs(s, c),
    }


def campaign_pcfs(s: Settings, c: Campaign) -> list[str]:
    """The campaign's own PCFs, its float PCF, and any other PCF that starts like it."""
    names = {c.pcf, c.float_pcf} | {p.stem for p in (s.gpsuser / "PCF").glob(f"{c.name[:2]}*.PCF")}
    return sorted(n for n in names if n and (s.gpsuser / "PCF" / f"{n}.PCF").is_file())


# --------------------------------------------------------------------------- saved plans


def plans_dir(s: Settings) -> Path:
    return s.state_dir / "plans"


def save_plan(s: Settings, body: dict, who: str) -> dict:
    record = {
        "id": dt.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6],
        "saved": dt.datetime.now().isoformat(timespec="seconds"),
        "by": who,
        **{
            k: body[k]
            for k in ("name", "campaign", "year", "from", "to", "pcf", "skipped", "rnxgra")
            if k in body
        },
    }
    d = plans_dir(s)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".{record['id']}.tmp"
    tmp.write_text(json.dumps(record, indent=2) + "\n")
    tmp.replace(d / f"{record['id']}.json")
    return record


def list_plans(s: Settings) -> list[dict]:
    out = []
    for p in sorted(plans_dir(s).glob("*.json"), reverse=True):
        try:
            out.append(json.loads(p.read_text()))
        except (OSError, json.JSONDecodeError):
            continue
    return out


# --------------------------------------------------------------------------- redo


def redo_preview(s: Settings, c: Campaign, year: int, doy: int) -> dict:
    """What a redo would move aside, and where. Read-only: the move is stage 3."""
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    base = year_dir(s, c.pcf, c.name, year)
    files = [r for r in day_results(s, c, year, doy) if r["path"]]
    return {
        **day_info(year, doy),
        "campaign": c.name,
        "from": str(base),
        "to": str(base / "SUPERSEDED" / stamp),
        "files": files,
        "lock": lock_status(s),
    }
