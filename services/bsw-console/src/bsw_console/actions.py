"""Stage 3: the console's run buttons, as requests in the run worker's queue.

The console never runs a BPE. Each button writes one validated request into the
queue `bernese-worker run` reads (bernese_workflow.run_queue) and answers with
its id; the worker carries it out under the BPE lock when it can. The design is
docs/project_documentation/run_worker_design.md.

THE GATE
Every action passes the same checks, in this order; the first that fails is the
answer, and nothing is queued:
1. BSW_CONSOLE_ACTIONS is not "on" (the default): 501 with the stage-3 reason.
   Off until personal accounts exist, because starting a BPE is the one thing
   the console does that cannot be undone.
2. Nobody is signed in: 403. Each request records who asked, and only a name
   from a trusted proxy's X-Remote-User counts.
3. The user is not in BSW_CONSOLE_OPERATORS: 403. An empty list lets nobody
   act, so turning actions on without naming operators does nothing.
4. No worker holds worker.lock: 503. A request queued with no worker would sit
   there with nobody told; refusing says so at the moment it matters.

WHAT EACH BUTTON QUEUES
start, preflight  the campaign's daily PCF over the days asked, under the
                  campaign's per-day prefix. The worker runs the PCF whole, so
                  a plan that skips steps, changes RNXGRA or names another PCF
                  is refused here (422) rather than run differently from what
                  the page showed. Those runs stay on the command line.
redo              one day, with the reason the page requires.
stop              the request the worker is running, after its current block.
                  A run started from the command line is not the worker's and
                  is stopped there (409).
"""

from __future__ import annotations

import json
from pathlib import Path

from bernese_workflow import run_queue
from fastapi import HTTPException

from .settings import Campaign, Settings
from .status import flock_held

STAGE3_REASON = (
    "Not enabled yet. The console queues runs for the run worker on gps3 "
    "(bernese-worker), and that is switched off until personal accounts exist, so "
    "every action is recorded with a name. Until then, runs are started on gps3 from "
    "the command line with bernese-run-year."
)


class ActionsOff(Exception):
    """Actions are switched off; the endpoint answers 501 with STAGE3_REASON."""


def queue(s: Settings) -> run_queue.Queue:
    return run_queue.Queue(s.worker_state)


def worker_status(s: Settings) -> dict:
    """Whether a worker holds the queue's worker.lock, and its last status.json."""
    q = queue(s)
    alive = flock_held(q.root / "worker.lock")
    try:
        last = json.loads((q.root / "status.json").read_text())
    except (OSError, ValueError):
        last = None
    return {"alive": alive, "status": last if isinstance(last, dict) else None}


def blockers(s: Settings, user: str) -> list[str]:
    """Why the gate would refuse ``user`` now, in the gate's order; empty if it would not."""
    if not s.actions_enabled:
        return ["starting runs from the console is switched off until personal accounts exist"]
    why = []
    if not user:
        why.append("nobody is signed in")
    elif user not in s.operators:
        why.append(f"{user} is not one of the console's operators")
    if not worker_status(s)["alive"]:
        why.append("no run worker is running on gps3")
    return why


def gate(s: Settings, user: str) -> None:
    """Raise unless ``user`` may queue a request now (see THE GATE)."""
    if not s.actions_enabled:
        raise ActionsOff
    if not user:
        raise HTTPException(403, "Sign in first: every run is recorded with who started it.")
    if user not in s.operators:
        raise HTTPException(403, f"{user} is not one of the console's operators.")
    if not worker_status(s)["alive"]:
        raise HTTPException(
            503,
            "No run worker is running on gps3, so nothing was queued. "
            "Start it with: sudo systemctl start bernese-worker",
        )


def _submit(s: Settings, kind: str, user: str, **fields: object) -> dict:
    try:
        req = run_queue.make_request(kind, user, **fields)
    except run_queue.InvalidRequest as exc:
        raise HTTPException(422, str(exc)) from None
    path: Path = queue(s).ensure().submit(req)
    return {"queued": req["id"], "kind": kind, "by": user, "file": path.name}


def _runnable(c: Campaign, pcf: object, skipped: object, rnxgra: object) -> None:
    if not c.prefix:
        raise HTTPException(
            422,
            f"{c.name} has no per-day campaign prefix configured, so it cannot run in parallel sessions.",
        )
    if pcf not in (None, "", c.pcf):
        raise HTTPException(
            422,
            f"The console starts {c.name}'s daily PCF, {c.pcf}, only. "
            f"Run {pcf} from the command line with bernese-run-year.",
        )
    if skipped:
        raise HTTPException(
            422,
            "The worker runs the whole PCF; a plan that skips steps runs from the command line.",
        )
    if rnxgra not in (None, "", "continuous"):
        raise HTTPException(
            422,
            "The worker runs RNXGRA as the PCF sets it; another preset runs from the command line.",
        )


def start(s: Settings, c: Campaign, user: str, kind: str, body: dict) -> dict:
    """Queue a start or a preflight for ``body``'s days."""
    gate(s, user)
    _runnable(c, body.get("pcf"), body.get("skipped"), body.get("rnxgra"))
    return _submit(
        s,
        kind,
        user,
        campaign=c.name,
        repr_prefix=c.prefix,
        pcf=c.pcf,
        year=body.get("year"),
        reason=str(body.get("reason") or ""),
        **{"from": body.get("from"), "to": body.get("to")},
    )


def redo(s: Settings, c: Campaign, user: str, body: dict) -> dict:
    gate(s, user)
    _runnable(c, None, None, None)
    return _submit(
        s,
        run_queue.REDO,
        user,
        campaign=c.name,
        repr_prefix=c.prefix,
        pcf=c.pcf,
        year=body.get("year"),
        doy=body.get("doy"),
        reason=str(body.get("reason") or ""),
    )


def stop(s: Settings, c: Campaign, user: str, body: dict) -> dict:
    """Queue a stop for the request the worker is running, if it is this campaign's."""
    gate(s, user)
    q = queue(s)
    active = (worker_status(s)["status"] or {}).get("active")
    found = q.find(active) if isinstance(active, str) else None
    if not found or found[0] != "active":
        raise HTTPException(
            409,
            "The run worker is not running a request. A run started from the command "
            "line is stopped there.",
        )
    try:
        req = json.loads(found[1].read_text())
    except (OSError, ValueError):
        raise HTTPException(409, "The running request could not be read.") from None
    if req.get("campaign") != c.name or req.get("year") != body.get("year"):
        raise HTTPException(
            409,
            f"The worker is running {req.get('campaign')} {req.get('year')}, not this run.",
        )
    return _submit(s, run_queue.STOP, user, target=active, reason=str(body.get("reason") or ""))
