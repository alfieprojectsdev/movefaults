"""The console's HTTP API, and the built frontend.

Stages 1 and 2 are wired: every GET reads the processing service's records,
and saving a plan writes one file in the console's own state directory.
Stage 3 (start, stop, redo, preflight) queues requests for the run worker
(bernese-worker) through bsw_console/actions.py. It is off unless
BSW_CONSOLE_ACTIONS=on, and even then only for a signed-in user listed in
BSW_CONSOLE_OPERATORS, and only while a worker is running; otherwise each
endpoint says why and queues nothing. The browser never sends a filesystem
path: it names a campaign, a year and a day, and the file viewer takes only a
name the server listed for that day.

Sign-in comes from a login proxy in front of the console (Caddy, on gps3). The
server binds to 127.0.0.1 by default and, with no proxy, says nobody is signed
in. X-Remote-User is believed only from an address listed in
BSW_CONSOLE_TRUSTED_PROXIES (none by default): any client can send the header,
so without a proxy in front it proves nothing.

The one write, saving a plan, accepts only a same-origin application/json body
of a few KB with known fields. A cross-site page can send a text/plain POST
without a CORS preflight; refusing every other content type is what stops that.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import actions, equipment, outliers, stations, status, timeseries
from . import plan as plans
from .actions import STAGE3_REASON
from .settings import Settings


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
    if s.actions_enabled and s.worker_state is None:
        logging.getLogger(__name__).warning(
            "BSW_CONSOLE_ACTIONS is on but BERNESE_WORKER_STATE is not set: the console "
            "looks for the worker under its own user's home. Set it to the directory "
            "`bernese-worker run` uses, writable by this user, on a local filesystem."
        )
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
        name = (request.headers.get("x-remote-user") or "").strip()
        # The proxy must send a bare username, the form run_queue records. An
        # email or anything else is nobody, not a name cut to fit.
        return name if actions.USERNAME.fullmatch(name) else ""

    @app.get("/api/session")
    def session(request: Request) -> dict:
        return {
            "user": who(request) or None,
            "version": version,
            "actions_enabled": s.actions_enabled,
            "can_act": not actions.blockers(s, who(request)),
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
        request: Request,
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
        out = plans.build(s, c, year, start, end, pcf=pcf, skipped=skipped, rnxgra=rnxgra)
        why = list(out["start_blocked_because"])
        mismatch = actions.plan_mismatch(c, pcf, skipped, rnxgra)
        if mismatch:
            why.append(mismatch)
        elif not actions.preflight_done(s, c, year, start, end):
            why.append("the preflight for these days has not finished ok")
        why += actions.blockers(s, who(request))
        return {**out, "start_blocked_because": why, "can_start": not why}

    @app.get("/api/plans")
    def saved_plans() -> dict:
        return {"plans": plans.list_plans(s)}

    @app.post("/api/plans")
    async def save(request: Request) -> dict:
        body = await _json_body(request)
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

    # Stage 5, read-only: pogf_geodetic_suite.timeseries.status, in this process.
    # The browser names a campaign and station codes; the CRDs are that
    # campaign's yearly result directories, never a path from the request.
    @app.get("/api/campaigns/{name}/time-series")
    def time_series_summary(name: str, reference: str | None = None) -> dict:
        return timeseries.summary(s, campaign(name), _station_code(reference))

    @app.get("/api/campaigns/{name}/time-series/{station}")
    def time_series(name: str, station: str, reference: str | None = None) -> dict:
        c = campaign(name)
        return timeseries.for_station(s, c, _station_code(station), _station_code(reference))

    # Outlier decisions (outlier_review_design.md): a signed-in person confirms
    # or overrides the rule's flag on one epoch. Appended, never edited; no CRD
    # or PLOT file is touched. Reading needs no sign-in, recording does.
    @app.get("/api/campaigns/{name}/time-series/{station}/decisions")
    def outlier_decisions(name: str, station: str, reference: str | None = None) -> dict:
        c = campaign(name)
        code = _station_code(station)
        return {
            "decisions": outliers.current(
                s, c, code, timeseries.crd_dirs(s, c), _station_code(reference)
            )
        }

    @app.post("/api/campaigns/{name}/time-series/{station}/decisions")
    async def record_outlier_decision(request: Request, name: str, station: str) -> JSONResponse:
        user = who(request)
        if not user:
            raise HTTPException(403, "Sign in first: every decision is recorded with who made it.")
        body = await _json_body(request)
        c = campaign(name)
        code = _station_code(station)
        row = outliers.record(
            s, c, code, timeseries.crd_dirs(s, c), user, body,
            lambda epoch, ref: timeseries.epoch_flag(s, c, code, ref, epoch),
        )  # fmt: skip
        return JSONResponse(row, status_code=201)

    # Stage 3: each queues one request for the run worker. The gate runs first,
    # before the body is read or the campaign looked up, so a refused caller
    # learns nothing else (actions.py, THE GATE).
    def off() -> JSONResponse:
        return JSONResponse({"enabled": False, "reason": STAGE3_REASON}, status_code=501)

    async def gated(request: Request, fn, *args) -> JSONResponse:
        user = who(request)
        try:
            actions.gate(s, user)
        except actions.ActionsOff:
            return off()
        body = await _json_body(request)
        c = campaign(str(body.get("campaign", "")))
        return JSONResponse(fn(s, c, user, *args, body), status_code=202)

    @app.post("/api/runs/start")
    async def run_start(request: Request) -> JSONResponse:
        return await gated(request, actions.start, "start")

    @app.post("/api/preflight")
    async def preflight(request: Request) -> JSONResponse:
        return await gated(request, actions.start, "preflight")

    @app.post("/api/redo")
    async def redo(request: Request) -> JSONResponse:
        return await gated(request, actions.redo)

    @app.post("/api/runs/stop")
    async def run_stop(request: Request) -> JSONResponse:
        return await gated(request, actions.stop)

    @app.get("/api/worker")
    def worker(request: Request) -> dict:
        return {
            **actions.worker_status(s),
            "actions_enabled": s.actions_enabled,
            "blocked_because": actions.blockers(s, who(request)),
        }

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
    # proxy_headers=False: the console decides whom to trust (X-Remote-User) by
    # the address that actually connected, which is Caddy's 127.0.0.1. With
    # uvicorn's default, a trusted local proxy's X-Forwarded-For replaces that
    # address with the browser's, so the sign-in proxy stops being recognised
    # and everyone shows as not signed in.
    uvicorn.run(create_app(), host=host, port=port, proxy_headers=False)


if __name__ == "__main__":
    start()


async def _json_body(request: Request) -> dict:
    """A same-origin JSON object of at most MAX_PLAN_BYTES, read as it streams.

    Reading the stream with a cutoff caps a chunked upload that declares no
    Content-Length; request.body() would buffer the whole of it first.
    """
    _same_origin_json(request)
    raw = bytearray()
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > MAX_PLAN_BYTES:
            raise HTTPException(413, f"a request body is at most {MAX_PLAN_BYTES} bytes")
    try:
        body = json.loads(bytes(raw))
    except ValueError:
        raise HTTPException(422, "the body is not JSON") from None
    if not isinstance(body, dict):
        raise HTTPException(422, "the body must be a JSON object")
    return body


def _station_code(code: str | None) -> str | None:
    """A four-character station code from the request, or None; never a path."""
    if code is None or code == "":
        return None
    if not re.fullmatch(r"[A-Za-z0-9]{4}", code):
        raise HTTPException(422, "a station code is four letters or digits")
    return code.upper()


def _check_year(year: int) -> None:
    if not 1980 <= year <= 2100:
        raise HTTPException(422, f"{year} is not a plausible campaign year")
