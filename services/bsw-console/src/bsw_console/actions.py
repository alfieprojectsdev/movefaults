"""Stage 3: the console's run buttons, as requests in the run worker's queue.

The console never runs a BPE. Each button writes one validated request into the
queue `bernese-worker run` reads (bernese_workflow.run_queue) and answers with
its id; the worker carries it out under the BPE lock when it can. The design is
docs/project_documentation/run_worker_design.md.

THE GATE
Every action passes the same checks, in this order; the first that fails is the
answer, and nothing is queued:
1. BSW_CONSOLE_ACTIONS is not "on" (the default): 501 with the stage-3 reason.
   Off unless asked for, because starting a BPE is the one thing the console
   does that cannot be undone.
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

import datetime as dt
import json
import re
from pathlib import Path

from bernese_workflow import run_queue
from fastapi import HTTPException

from . import plan as plans
from . import status
from .settings import Campaign, Settings
from .status import flock_held

STAGE3_REASON = (
    "Not enabled on this console. The console queues runs for the run worker on "
    "gps3 (bernese-worker), and that is switched off here (BSW_CONSOLE_ACTIONS). "
    "Runs are started on gps3 from the command line with bernese-run-year."
)


class ActionsOff(Exception):
    """Actions are switched off; the endpoint answers 501 with STAGE3_REASON."""


# run_queue's own rule for submitted_by. A name the queue would refuse is not a
# signed-in user here either, so the gate and the queue cannot disagree.
USERNAME = re.compile(r"[A-Za-z0-9._-]{1,64}")

# A preflight older than this no longer opens Start: the products, station
# files or panels it checked may have changed since.
PREFLIGHT_MAX_AGE = dt.timedelta(days=7)


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


def email_alerts(s: Settings, user: str = "", now: dt.datetime | None = None) -> dict[str, str]:
    """Whether bernese-notify is working and will reach ``user``, for the Plan page, so
    that silence isn't mistaken for "all fine". The text names no address and no mail
    error: the details are in <worker state>/notify/status.json."""
    try:
        last = json.loads((queue(s).root / "notify" / "status.json").read_text())
        at = dt.datetime.fromisoformat(last["last_pass"])
        errors = len(last.get("errors", []))
        age = ((now or dt.datetime.now(dt.UTC)) - at).total_seconds() / 60
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {"state": "off", "text": "Email alerts are not running: nobody will be emailed about this run."}
    if age > 30:
        return {
            "state": "stale",
            "text": f"Email alerts last checked {age:.0f} minutes ago, so they may have stopped.",
        }
    if errors:
        return {"state": "failing", "text": f"Email alerts had {errors} problem(s) on their last check, so a message may not have reached everyone."}
    operators = last.get("operators")
    if user and isinstance(operators, list) and user.upper() not in operators:
        return {"state": "no-address", "text": f"The maintainer is emailed about this run, but no address is on file for {user}, so you won't be."}
    return {"state": "ok", "text": "You and the maintainer are emailed when this run starts, every few hours, and when it ends or has a problem."}


def gate_failures(s: Settings, user: str) -> list[tuple[int, str]]:
    """THE GATE, as (status, message) pairs in order; empty when ``user`` may act.

    The one statement of the rule: gate() raises the first, blockers() lists
    them all for the Plan page.
    """
    if not s.actions_enabled:
        return [
            (501, "starting runs from this console is switched off (BSW_CONSOLE_ACTIONS)")
        ]
    out: list[tuple[int, str]] = []
    if not user:
        out.append((403, "nobody is signed in: every run is recorded with who started it"))
    elif user not in s.operators:
        out.append((403, f"{user} is not one of the console's operators"))
    if not worker_status(s)["alive"]:
        out.append(
            (503, "no run worker is running on gps3, so nothing can be queued "
                  "(sudo systemctl start bernese-worker)")
        )  # fmt: skip
    return out


def blockers(s: Settings, user: str) -> list[str]:
    return [msg for _, msg in gate_failures(s, user)]


def gate(s: Settings, user: str) -> None:
    """Raise unless ``user`` may queue a request now (see THE GATE)."""
    failures = gate_failures(s, user)
    if not failures:
        return
    code, msg = failures[0]
    if code == 501:
        raise ActionsOff
    raise HTTPException(code, msg[0].upper() + msg[1:] + ".")


def plan_mismatch(c: Campaign, pcf: object, skipped: object, rnxgra: object) -> str | None:
    """Why the worker would run this plan differently from what the page shows, or None."""
    if not c.prefix:
        return f"{c.name} has no per-day campaign prefix configured, so it cannot run in parallel sessions"
    if pcf not in (None, "", c.pcf):
        return f"the console starts {c.name}'s daily PCF, {c.pcf}, only; run {pcf} from the command line"
    if skipped:
        return "the worker runs the whole PCF; a plan that skips steps runs from the command line"
    if rnxgra not in (None, "", "continuous"):
        return (
            "the worker runs RNXGRA as the PCF sets it; another preset runs from the command line"
        )
    return None


def preflight_done(s: Settings, c: Campaign, year: object, a: object, b: object) -> dict | None:
    """The newest successful preflight for exactly these days, if recent enough."""
    q = queue(s)
    if not q.done.is_dir():
        return None
    now = run_queue.now_utc()
    best = None
    for p in q.done.glob("*.json"):
        try:
            r = json.loads(p.read_text())
            finished = dt.datetime.fromisoformat(r["finished"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if (
            r.get("kind") == run_queue.PREFLIGHT
            and r.get("outcome") == "ok"
            and (r.get("campaign"), r.get("year"), r.get("pcf")) == (c.name, year, c.pcf)
            and (r.get("from"), r.get("to")) == (a, b)
            # A preflight run under the other header rule says nothing about this one.
            and (r.get("allow_header_mismatches") is True) == c.allow_header_mismatches
            and now - finished <= PREFLIGHT_MAX_AGE
            and (best is None or r["finished"] > best["finished"])
        ):
            best = r
    return best


def _int(body: dict, key: str) -> int:
    v = body.get(key)
    if not isinstance(v, int) or isinstance(v, bool):
        raise HTTPException(422, f"{key} must be a whole number")
    return v


def _submit(s: Settings, kind: str, user: str, **fields: object) -> dict:
    try:
        req = run_queue.make_request(kind, user, **fields)
    except run_queue.InvalidRequest as exc:
        raise HTTPException(422, str(exc)) from None
    path: Path = queue(s).ensure().submit(req)
    return {"queued": req["id"], "kind": kind, "by": user, "file": path.name}


def _options(c: Campaign) -> dict:
    """The campaign's run options, as request fields. Only those set, so a
    request for any other campaign is the same as before."""
    return {"allow_header_mismatches": True} if c.allow_header_mismatches else {}


def start(s: Settings, c: Campaign, user: str, kind: str, body: dict) -> dict:
    """Queue a start or a preflight for ``body``'s days. The caller has passed gate()."""
    why = plan_mismatch(c, body.get("pcf"), body.get("skipped"), body.get("rnxgra"))
    if why:
        raise HTTPException(422, why[0].upper() + why[1:] + ".")
    year, a, b = _int(body, "year"), _int(body, "from"), _int(body, "to")
    try:
        planned = plans.build(s, c, year, a, b)
    except (OSError, ValueError, KeyError, SystemExit) as exc:
        raise HTTPException(422, f"The plan could not be built: {exc}") from None
    bad = [x["title"] for x in planned["checks"] if x["level"] == "bad"]
    if bad:
        raise HTTPException(409, "The plan's checks fail: " + "; ".join(bad) + ".")
    if kind == run_queue.START and not preflight_done(s, c, year, a, b):
        raise HTTPException(
            409,
            "Queue a preflight for these days first; Start opens once it has finished ok "
            f"(within the last {PREFLIGHT_MAX_AGE.days} days).",
        )
    return _submit(
        s, kind, user, campaign=c.name, repr_prefix=c.prefix, pcf=c.pcf, year=year,
        reason=str(body.get("reason") or ""), **{"from": a, "to": b}, **_options(c),
    )  # fmt: skip


def redo(s: Settings, c: Campaign, user: str, body: dict) -> dict:
    """Queue a redo of one day. The caller has passed gate()."""
    why = plan_mismatch(c, None, None, None)
    if why:
        raise HTTPException(422, why[0].upper() + why[1:] + ".")
    return _submit(
        s, run_queue.REDO, user, campaign=c.name, repr_prefix=c.prefix, pcf=c.pcf,
        year=body.get("year"), doy=body.get("doy"), reason=str(body.get("reason") or ""),
        **_options(c),
    )  # fmt: skip


def stop(s: Settings, c: Campaign, user: str, body: dict) -> dict:
    """Queue a stop for the worker's running request, if it is the run the page shows.

    The page names a ledger run. The worker tags the run_start it writes with
    its request id, so the stop goes ahead only when that run is the one the
    worker is running; any other run (a command-line one, or a stale page) is
    stopped where it was started.
    """
    run = body.get("run")
    if not isinstance(run, str) or not run:
        raise HTTPException(422, "name the run to stop")
    year = _int(body, "year")
    active = (worker_status(s)["status"] or {}).get("active")
    found = queue(s).find(active) if isinstance(active, str) else None
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
    if req.get("campaign") != c.name or req.get("year") != year:
        raise HTTPException(
            409, f"The worker is running {req.get('campaign')} {req.get('year')}, not this run."
        )
    mine = [
        e.get("run")
        for e in status.read_ledger(status.ledger_path(s, c, year))
        if e.get("event") == "run_start" and e.get("request") == active
    ]
    if run not in mine:
        raise HTTPException(
            409,
            f"Run {run} is not the one the worker is running, so it was not stopped. "
            "A run started from the command line is stopped there.",
        )
    return _submit(s, run_queue.STOP, user, target=active, reason=str(body.get("reason") or ""))
