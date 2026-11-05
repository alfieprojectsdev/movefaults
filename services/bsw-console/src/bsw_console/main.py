"""The console's HTTP API, and the built frontend.

Stages 1 and 2 are wired: every GET reads the processing service's records,
and saving a plan writes one file in the console's own state directory.
Stage 3 (start, stop, redo, preflight) answers 501 with the reason. The run
worker that will carry those requests out under the BPE lock exists
(bernese_workflow.run_worker, `bernese-worker`, #316), but this console is not
wired to it yet, no worker runs as a service on gps3, and per-person accounts,
so every action is recorded with a name, are still pending. The browser never
sends a filesystem path: it names a campaign, a year and a day, and the file
viewer takes only a name the server listed for that day.

Sign-in is pending too (personal accounts on gps3 are a prerequisite in the
brief). Until then the server binds to 127.0.0.1 by default and says nobody is
signed in. X-Remote-User is believed only from an address listed in
BSW_CONSOLE_TRUSTED_PROXIES (none by default): any client can send the header,
so without a proxy in front it proves nothing.

The one write, saving a plan, accepts only a same-origin application/json body
of a few KB with known fields. A cross-site page can send a text/plain POST
without a CORS preflight; refusing every other content type is what stops that.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import equipment, stations, status
from . import plan as plans
from .settings import Settings

STAGE3_REASON = (
    "Not enabled yet. The run worker that starts, stops and redoes runs under the BPE "
    "lock exists on gps3 (bernese-worker), but this console is not connected to it yet, "
    "and personal accounts, so every action is recorded with a name, are still pending. "
    "Until then, runs are started on gps3 from the command line with bernese-run-year."
)


def _version() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or Settings.from_env()
    app = FastAPI(title="BSW 5.4 processing console", version="0.1")
    version = _version()

    def campaign(name: str):
        try:
            return s.campaign(name)
        except KeyError:
            raise HTTPException(404, f"no campaign {name}") from None

    def who(request: Request) -> str:
        client = request.client.host if request.client else ""
        if client not in s.trusted_proxies:
            return ""
        return (request.headers.get("x-remote-user") or "").strip()[:64]

    @app.get("/api/session")
    def session(request: Request) -> dict:
        return {
            "user": who(request) or None,
            "accounts": "pending",
            "version": version,
            "actions_enabled": s.actions_enabled,
            "campaigns": [c.name for c in s.campaigns],
        }

    @app.get("/api/lock")
    def lock() -> dict:
        lk = status.lock_status(s)
        live = None
        for c in s.campaigns:
            for y in status.campaign_years(s, c):
                runs = status.runs_in(status.read_ledger(status.ledger_path(s, c, y)))
                if runs and runs[0]["state"] in ("running", "slow", "unknown"):
                    r = runs[0]
                    done = sum(
                        1
                        for a in status.attempts(status.read_ledger(status.ledger_path(s, c, y)))
                        if a.run == r["run"] and a.outcome
                    )
                    live = {
                        "campaign": c.name,
                        "year": y,
                        "run": r["run"],
                        "doys": [min(r["doys"]), max(r["doys"])] if r["doys"] else [],
                        "done": done,
                        "total": len(r["doys"]),
                        "started": r["started"],
                    }
        return {**lk, "run": live}

    @app.get("/api/campaigns")
    def campaigns() -> dict:
        return {
            "campaigns": [status.campaign_summary(s, c) for c in s.campaigns],
            "activity": status.activity(s),
        }

    @app.get("/api/campaigns/{name}/years/{year}/days")
    def calendar(name: str, year: int) -> dict:
        return status.day_states(s, campaign(name), year)

    @app.get("/api/campaigns/{name}/years/{year}/runs")
    def run(name: str, year: int, run: str | None = None) -> dict:
        try:
            return status.run_detail(s, campaign(name), year, run)
        except KeyError:
            raise HTTPException(404, f"no run {run}") from None

    @app.get("/api/campaigns/{name}/years/{year}/days/{doy}")
    def day(name: str, year: int, doy: int) -> dict:
        _check_doy(year, doy)
        return status.day_detail(s, campaign(name), year, doy)

    @app.get("/api/campaigns/{name}/years/{year}/days/{doy}/file")
    def day_file(name: str, year: int, doy: int, path: str) -> dict:
        _check_doy(year, doy)
        try:
            return status.read_day_file(s, campaign(name), year, doy, path)
        except KeyError:
            raise HTTPException(404, f"{path} is not a file of this day") from None

    @app.get("/api/campaigns/{name}/years/{year}/days/{doy}/failure")
    def failure(name: str, year: int, doy: int) -> dict:
        _check_doy(year, doy)
        try:
            return status.failure(s, campaign(name), year, doy)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from None

    @app.get("/api/campaigns/{name}/years/{year}/days/{doy}/redo")
    def redo_preview(name: str, year: int, doy: int) -> dict:
        _check_doy(year, doy)
        return plans.redo_preview(s, campaign(name), year, doy)

    @app.get("/api/campaigns/{name}/years/{year}/plan")
    def plan(
        name: str,
        year: int,
        start: int,
        end: int,
        pcf: str | None = None,
        skip: str = "",
        rnxgra: str = "continuous",
    ) -> dict:
        _check_doy(year, start)
        _check_doy(year, end)
        if start > end:
            raise HTTPException(422, "the first day is after the last")
        c = campaign(name)
        # A PCF is named, never given as a path: letters, digits and _ only.
        if pcf is not None and (
            not re.fullmatch(r"[A-Za-z0-9_]+", pcf)
            or not (s.gpsuser / "PCF" / f"{pcf}.PCF").is_file()
        ):
            raise HTTPException(404, f"no PCF {pcf}")
        skipped = {int(x) for x in skip.split(",") if x.strip().isdigit()}
        return plans.build(s, c, year, start, end, pcf=pcf, skipped=skipped, rnxgra=rnxgra)

    @app.get("/api/plans")
    def saved_plans() -> dict:
        return {"plans": plans.list_plans(s)}

    @app.post("/api/plans")
    async def save(request: Request) -> dict:
        _same_origin_json(request)
        raw = await request.body()
        if len(raw) > MAX_PLAN_BYTES:
            raise HTTPException(413, f"a plan is at most {MAX_PLAN_BYTES} bytes")
        try:
            body = json.loads(raw)
        except ValueError:
            raise HTTPException(422, "the body is not JSON") from None
        clean = _valid_plan(s, body)
        return plans.save_plan(s, clean, who(request) or "not signed in")

    @app.get("/api/known-errors")
    def known_errors() -> dict:
        return status.known_errors(s)

    @app.get("/api/campaigns/{name}/years/{year}/station-files")
    def station_files(name: str, year: int) -> dict:
        return stations.coverage(s, campaign(name), year)

    # Read-only: what bernese-check-equipment reported. The browser names a
    # four-character code; the report file is the server's setting, never a path
    # from the request.
    @app.get("/api/equipment-report")
    def equipment_report() -> dict:
        return equipment.summary(s)

    @app.get("/api/stations/{code}/equipment")
    def station_equipment(code: str) -> dict:
        if not re.fullmatch(r"[A-Za-z0-9]{4}", code):
            raise HTTPException(422, "a station code is four letters or digits")
        return equipment.for_station(s, code)

    @app.get("/api/campaigns/{name}/time-series/{station}")
    def time_series(name: str, station: str) -> JSONResponse:
        campaign(name)
        return JSONResponse(
            {
                "connected": False,
                "reason": "The time-series panel waits on a read-only status endpoint from the timeseries package (stage 5).",
            },
            status_code=501,
        )

    # Stage 3. Each answers 501 until the console is wired to the run worker.
    for route in ("/api/runs/start", "/api/runs/stop", "/api/preflight", "/api/redo"):

        @app.post(route)
        def not_yet() -> JSONResponse:
            return JSONResponse({"enabled": False, "reason": STAGE3_REASON}, status_code=501)

    if s.static_dir is not None:
        index = s.static_dir / "index.html"
        app.mount(
            "/assets",
            StaticFiles(directory=s.static_dir / "assets", check_dir=False),
            name="assets",
        )

        @app.get("/{rest:path}", include_in_schema=False)
        def spa(rest: str) -> FileResponse:
            if rest.startswith("api/"):
                raise HTTPException(404)
            return FileResponse(index)

    return app


MAX_PLAN_BYTES = 4096
_PLAN_FIELDS = {"name", "campaign", "year", "from", "to", "pcf", "skipped", "rnxgra"}


def _same_origin_json(request: Request) -> None:
    """Refuse a write a page on another site could have sent.

    Browsers send text/plain, form and multipart POSTs cross-site without a
    preflight. application/json needs one, and no CORS policy here allows it.
    An Origin or Sec-Fetch-Site naming another site is refused outright.
    """
    ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if ctype != "application/json":
        raise HTTPException(415, "send application/json")
    if request.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
        raise HTTPException(403, "cross-site request refused")
    origin = request.headers.get("origin")
    if origin is not None and urlsplit(origin).netloc != request.headers.get("host", ""):
        raise HTTPException(403, "cross-origin request refused")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_PLAN_BYTES:
        raise HTTPException(413, f"a plan is at most {MAX_PLAN_BYTES} bytes")


def _valid_plan(s: Settings, body: object) -> dict:
    """The saved fields, typed and bounded; anything else is a 4xx."""
    if not isinstance(body, dict):
        raise HTTPException(422, "a plan is a JSON object")
    unknown = set(body) - _PLAN_FIELDS
    if unknown:
        raise HTTPException(422, f"unknown field(s): {', '.join(sorted(unknown))}")

    def integer(key: str) -> int:
        v = body.get(key)
        if not isinstance(v, int) or isinstance(v, bool):
            raise HTTPException(422, f"{key} must be a whole number")
        return v

    try:
        c = s.campaign(str(body.get("campaign", ""))[:32])
    except KeyError:
        raise HTTPException(404, "no such campaign") from None
    year = integer("year")
    if not 1980 <= year <= 2100:
        raise HTTPException(422, "year out of range")
    first, last = integer("from"), integer("to")
    _check_doy(year, first)
    _check_doy(year, last)
    if first > last:
        raise HTTPException(422, "the first day is after the last")
    out: dict = {"campaign": c.name, "year": year, "from": first, "to": last}
    if "name" in body:
        name = body["name"]
        if not isinstance(name, str) or len(name) > 100:
            raise HTTPException(422, "name must be text of at most 100 characters")
        out["name"] = name
    if body.get("pcf") is not None:
        pcf = body["pcf"]
        if not isinstance(pcf, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,32}", pcf):
            raise HTTPException(422, "pcf must be a PCF name")
        out["pcf"] = pcf
    if "skipped" in body:
        sk = body["skipped"]
        if (
            not isinstance(sk, list)
            or len(sk) > 10
            or any(not isinstance(x, int) or isinstance(x, bool) or not 0 <= x <= 9 for x in sk)
        ):
            raise HTTPException(422, "skipped must be a list of step groups 0-9")
        out["skipped"] = sorted(set(sk))
    if "rnxgra" in body:
        if body["rnxgra"] not in plans.RNXGRA_PRESETS:
            raise HTTPException(422, "rnxgra must be one of the presets")
        out["rnxgra"] = body["rnxgra"]
    return out


def _check_doy(year: int, doy: int) -> None:
    if not 1 <= doy <= status.days_in_year(year):
        raise HTTPException(422, f"DOY {doy} is not in {year}")


def start() -> None:
    import uvicorn

    host = os.environ.get("BSW_CONSOLE_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8002"))
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    start()
