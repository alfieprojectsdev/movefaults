"""The console's HTTP API, and the built frontend.

Stages 1 and 2 are wired: every GET reads the processing service's records,
and saving a plan writes one file in the console's own state directory.
Stage 3 (start, stop, redo, preflight) answers 501 with the reason: it needs a
run worker that holds the BPE lock and per-person accounts, and neither exists
yet. The browser never sends a path; it names a campaign, a year and a day.

Sign-in is pending too (personal accounts on gps3 are a prerequisite in the
brief). Until then the server binds to 127.0.0.1 by default and shows whoever
a fronting proxy names in X-Remote-User, or says nobody is signed in.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import plan as plans
from . import stations, status
from .settings import Settings

STAGE3_REASON = (
    "Not enabled yet. Starting, stopping and redoing runs from the console needs a run "
    "worker on gps3 that holds the BPE lock, and personal accounts so every action is "
    "recorded with a name. Until both exist, runs are started by the maintainer with "
    "bernese-run-year."
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
        return request.headers.get("x-remote-user") or ""

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
        body = await request.json()
        campaign(str(body.get("campaign", "")))
        return plans.save_plan(s, body, who(request) or "not signed in")

    @app.get("/api/known-errors")
    def known_errors() -> dict:
        return status.known_errors(s)

    @app.get("/api/campaigns/{name}/years/{year}/station-files")
    def station_files(name: str, year: int) -> dict:
        return stations.coverage(s, campaign(name), year)

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

    # Stage 3. Each answers 501 until the run worker exists.
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
