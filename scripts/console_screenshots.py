#!/usr/bin/env python3
"""Retake the BSW console screenshots in the work instruction.

    (cd services/bsw-console/frontend && npm ci && npm run build)
    uv run --extra dev --extra bsw-console --with playwright==1.64.1 \
        python scripts/console_screenshots.py

Run it when a screen the instruction shows has changed. It needs Playwright's
Chromium (`uv run --with playwright==1.64.1 playwright install chromium`).

THE DATA IS THE TEST SUITE'S, NOT GPS3'S. This repository is public, so anything in
an image is published. The console runs here on the test suite's made-up tree
(services/bsw-console/tests/conftest.py) plus a made-up time series below, in a
scratch folder, on a free port, with its own state, signed in as "demo". It never
reads gps3's data and cannot queue a real run or write to the real decision record.
One thing on screen is real: the Failure page's protocol file is the HELMR1 failure
captured from LZY250360, a fixture already committed under
services/bernese-workflow/tests/fixtures/bpe_errors, with gps3's paths in it.
"""

from __future__ import annotations

import argparse
import dataclasses
import fcntl
import random
import shutil
import socket
import sys
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import Page, sync_playwright

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(REPO / "services/bsw-console/tests"),
    str(REPO / "services/bernese-workflow/tests"),
]

from bsw_console.main import create_app  # noqa: E402
from bsw_console.plan import PRODUCTS  # noqa: E402
from bsw_console.settings import Settings  # noqa: E402
from station_fixtures import abb_text, atl_text, sta_text  # noqa: E402

from conftest import build  # noqa: E402

SCRATCH = Path("/tmp/bsw-console-demo")  # fixed, so the paths on screen do not change
USER = "demo"
REF = (-3186000.0, 5345000.0, 1640000.0)
EQ = 2024.5
SPIKE = (2025, 100)
YEAR = 2025
HEAD = (
    "SYNTHETIC NETWORK\n" + "-" * 80 + "\nLOCAL GEODETIC DATUM: IGS20\n\n"
    " NUM  STATION NAME           X (M)          Y (M)          Z (M)     FLAG     SYSTEM\n\n"
)


def _row(i: int, name: str, xyz: tuple[float, float, float]) -> str:
    x, y, z = xyz
    return f"{i:3d}  {name} 00000S000  {x:>15.5f} {y:>15.5f}  {z:>15.5f}    A   G\n"


def time_series(savedisk: Path, root: Path) -> Path:
    """Three years of noisy daily positions for a made-up station, one step at an
    earthquake and one large spike. Seeded, so a retake draws the same plot."""
    rng = random.Random(20261105)
    for old in ("2020", "2021"):
        shutil.rmtree(savedisk / "LUZON" / old, ignore_errors=True)
    for year in (2023, 2024, 2025):
        sta = savedisk / "LUZON" / str(year) / "STA"
        sta.mkdir(parents=True, exist_ok=True)
        for doy in range(1, 366):
            if rng.random() < 0.04:  # a real series has gaps
                continue
            t = year + doy / 365.25
            dy, dz = 0.022 * (t - 2023), -0.006 * (t - 2023)
            if t >= EQ:
                dy, dz = dy + 0.018, dz - 0.007
            if (year, doy) == SPIKE:
                dy += 0.12
            dy += rng.gauss(0, 0.0022)
            dz += rng.gauss(0, 0.0035)
            xyz = (REF[0] + 12000.0, REF[1] - 8000.0 + dy, REF[2] + 5000.0 + dz)
            (sta / f"FIN_{year}{doy:03d}0.CRD").write_text(
                HEAD + _row(1, "REF0", REF) + _row(2, "SYN1", xyz), encoding="ascii"
            )
    offsets = root / "offsets"
    offsets.write_text(f"# synthetic\nSYN1  {EQ:.4f}  EQ\n", encoding="utf-8")
    return offsets


def more_days(savedisk: Path) -> None:
    """Fill the calendar: copies of the one solved fixture day."""
    sol = savedisk / "LUZON" / str(YEAR) / "SOL"
    for name in ("FIN_20250350.SNX.gz", "FIN_20250350.NQ0.gz"):
        for doy in [*range(1, 35), *range(38, 120)]:
            shutil.copy(sol / name, sol / name.replace("20250350", f"{YEAR}{doy:03d}0"))


def plan_inputs(s: Settings) -> None:
    """What the Plan page checks, so its screen shows a plan that could run: every
    product, three reference stations with RINEX, and one day short of them. NEW1 is
    in no RINEX and missing from the BLQ, so Station files has a real gap to show."""
    ref = s.datapool / "REF54"
    observed = ["ALBU", "BILI", "IGS1", "IGS2", "IGS3"]
    full = {code: f"{code} 00000M001" for code in [*observed, "NEW1"]}
    (ref / "IGS20.FIX").write_text(
        "IGS20: synthetic reference set\n-----\n\nStation name\n****************\n"
        + "".join(f"{full[c]}\n" for c in ("IGS1", "IGS2", "IGS3"))
    )
    (ref / "LUZON.STA").write_text(
        "TYPE 001: RENAMING OF STATIONS\n\nSTATION NAME\n*****\n"
        + "".join(f"{name}  001\n" for name in full.values())
        + "\n"
        + sta_text([(name, "2000 01 01 00 00 00", "") for name in full.values()])
    )
    (ref / "LUZON.CRD").write_text(
        "SYNTHETIC\n----\nLOCAL GEODETIC DATUM: IGS20\n\nNUM  STATION NAME\n\n"
        + "".join(f"{i:3d}  {name}  1.0 2.0 3.0    A\n" for i, name in enumerate(full.values(), 1))
    )
    (ref / "LUZON.ABB").write_text(abb_text(list(full.values())))
    (ref / "LUZON.ATL").write_text(atl_text(list(full.values())))
    (ref / "LUZON.BLQ").write_text(
        "$$ synthetic\n"
        + "".join(f"  {c}               {c}\n  .01 .02\n" for c in observed)
        + "$$ END TABLE\n"
    )
    (ref / "LUZON.CLU").write_text(abb_text(list(full.values())))
    for ext in ("PLD", "VEL"):
        (ref / f"LUZON.{ext}").write_text(
            "SYNTHETIC\n----\n\nNUM  STATION NAME\n\n"
            + "".join(f"{i:3d}  {name}  1.0\n" for i, name in enumerate(full.values(), 1))
        )
    (s.gpsuser / "OPT" / "R2S_FIN").mkdir(parents=True, exist_ok=True)
    (s.gpsuser / "OPT" / "R2S_FIN" / "ADDNEQ2.INP").write_text('MAXPAR 1 "3000"\n')
    rinex = s.datapool / "LUZON"
    rinex.mkdir(exist_ok=True)
    for doy in range(35, 41):
        here = observed[:-1] if doy == 38 else observed  # one day short of a reference
        for code in here:
            (rinex / f"{code.lower()}{doy:03d}0.{YEAR % 100}o").write_text("x\n")
        for _, folder, pattern in PRODUCTS:
            (s.datapool / folder).mkdir(exist_ok=True)
            (s.datapool / folder / pattern.format(y=YEAR, d=f"{doy:03d}")).write_text("x\n")


def settings() -> Settings:
    dist = REPO / "services/bsw-console/frontend/dist"
    if not (dist / "index.html").is_file():
        raise SystemExit(f"no frontend build in {dist}: see this script's header")
    shutil.rmtree(SCRATCH, ignore_errors=True)
    SCRATCH.mkdir(parents=True)
    s = build(SCRATCH)
    offsets = time_series(s.savedisk, SCRATCH)
    more_days(s.savedisk)
    plan_inputs(s)
    return dataclasses.replace(
        s,
        ts_offsets=offsets,
        trusted_proxies=frozenset({"127.0.0.1"}),
        static_dir=dist,
        # The buttons as gps3 has them. Nothing here presses Start, and this
        # queue is in the scratch folder, so nothing would run if it did.
        actions_enabled=True,
        operators=frozenset({USER}),
        worker_state=SCRATCH / "worker",
    )


def pretend_worker(s: Settings):
    """Hold worker.lock, which is how the console knows a worker is alive."""
    s.worker_state.mkdir(parents=True, exist_ok=True)
    fh = open(s.worker_state / "worker.lock", "w")  # noqa: SIM115
    fcntl.flock(fh, fcntl.LOCK_EX)
    return fh


def serve(s: Settings) -> tuple[str, uvicorn.Server]:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(s), host="127.0.0.1", port=port, proxy_headers=False, log_level="warning"
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            return f"http://127.0.0.1:{port}", server
        if not thread.is_alive():
            break
        time.sleep(0.1)
    raise SystemExit("the console did not start")


def open_route(page: Page, url: str, route: str) -> None:
    """Load the route from nothing. Going from one hash route to another is not a
    navigation: goto returns at once, networkidle has already fired, and the previous
    page is still on screen, so a wait for its text would pass and shoot the wrong page."""
    page.goto("about:blank")
    page.goto(f"{url}/{route}")


def shoot(page: Page, url: str, route: str, out: Path, wait_for: str, click_day: int = 0) -> None:
    open_route(page, url, route)
    page.get_by_text(wait_for).first.wait_for(timeout=20000)
    page.wait_for_load_state("networkidle")
    if click_day:
        page.locator(f'[aria-label*="DOY {click_day:03d}"]').first.click()
        page.wait_for_timeout(300)
    page.screenshot(path=out, full_page=True)
    print(f"{out}  {out.stat().st_size // 1024} KB")


def time_series_shots(page: Page, url: str, out: Path) -> None:
    """The decision form on the flagged spike, then the whole page once it is
    recorded, on this scratch console, so the ring and the not-published fit show."""
    open_route(page, url, f"#/c/LUZON/{YEAR}/time-series")
    page.locator("label", has_text="Station").locator("select").last.select_option("SYN1")
    page.wait_for_selector("[data-testid=ts-plot] canvas", timeout=20000)
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name=str(SPIKE[0]), exact=True).click()
    box = page.locator(".u-over").first.bounding_box()
    epoch = f"{SPIKE[0]}-{SPIKE[1]:03d}"
    # The button shows one year across the panel, and a click picks the nearest epoch.
    middle = box["x"] + box["width"] * (SPIKE[1] - 1) / 365.0
    for dx in (0, 1, -1, 2, -2, 3, -3, 4, -4):
        page.mouse.move(middle + dx, box["y"] + box["height"] / 2)
        page.wait_for_timeout(100)
        page.mouse.click(middle + dx, box["y"] + box["height"] / 2)
        page.locator("#ts-decide").wait_for(timeout=20000)
        if epoch in page.locator("#ts-decide").inner_text():
            break
    else:
        raise SystemExit(f"could not click {epoch}")
    # The buttons need /api/session, which the form only starts to fetch once it opens.
    page.get_by_role("button", name="Confirm outlier").wait_for(timeout=20000)
    # The plot with the popup beside its point, which is what the image is for.
    page.locator('[data-testid="ts-plot"]').locator("..").screenshot(
        path=out / "outlier_decision.png"
    )
    page.get_by_role("button", name="Confirm outlier").click()
    page.get_by_text("(not published)").first.wait_for(timeout=20000)
    page.get_by_role("button", name="All years").click()
    page.wait_for_timeout(300)
    page.screenshot(path=out / "time_series.png", full_page=True)
    print(out / "outlier_decision.png", out / "time_series.png")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=REPO / "docs/images/bsw_console")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    s = settings()
    worker = pretend_worker(s)
    url, server = serve(s)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(
                viewport={"width": 1400, "height": 800},
                color_scheme="light",
                extra_http_headers={"X-Remote-User": USER},
            )
            page = context.new_page()
            base = f"#/c/LUZON/{YEAR}"
            shoot(page, url, base, args.out / "calendar.png", "Fixed", click_day=36)
            shoot(
                page,
                url,
                f"{base}/plan?from=35&to=40",
                args.out / "plan.png",
                "Checks before the run",
            )
            shoot(page, url, f"{base}/run", args.out / "runs.png", "solved")
            shoot(page, url, f"{base}/day/35", args.out / "day.png", "HELMCHK RMS")
            shoot(page, url, f"{base}/day/36/failure", args.out / "failure.png", "PID and script")
            shoot(page, url, f"{base}/stations", args.out / "station_files.png", "BLQ")
            time_series_shots(page, url, args.out)
            browser.close()
    finally:
        server.should_exit = True
        worker.close()
        shutil.rmtree(SCRATCH, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
