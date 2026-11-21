#!/usr/bin/env python3
"""Record the BSW console feature demo: what changes from BSW 5.2 to the console.

    (cd services/bsw-console/frontend && npm ci && npm run build)
    uv run --extra dev --extra bsw-console --with playwright==1.64.1 \
        python scripts/console_demo.py --out ~/bsw-console-demo

It needs Playwright's Chromium (`uv run --with playwright==1.64.1 playwright install
chromium`) and Linux: the console's test setup takes a lock with fcntl, so on Windows
run it under WSL. It writes demo.webm and demo.srt to --out, which must be outside the
repository (*.mp4 is gitignored here, and the video is not repository material), and
converts to demo.mp4 when an ffmpeg with libx264 is on PATH; otherwise it prints the
command to run.

RE-RECORDING. Run it again after a page in the video changes. The scenes, their text
and how long each holds are in SCENES and CARDS below. Every 5.2 claim on screen comes
from docs/bsw_console_work_instruction.md, which follows the 5.2 work instruction's
section numbers; check a changed claim against it, and the results and open questions
against docs/SETTLED.md, before re-recording. Then look at a frame every 5 seconds:
ffmpeg -i demo.mp4 -vf fps=1/5 frame_%03d.png

THE DATA IS THE TEST SUITE'S, NOT GPS3'S, through scripts/console_screenshots.py: the
same made-up tree, scratch folder, free port and "demo" sign-in. Nothing here can queue
a real run or write to the real decision record: Queue preflight and the outlier
decision go to the scratch folder. Two things on the Failure page are real, and its
captions say so: the known-errors entry, and the protocol file, a captured failure with
gps3's paths in it; its header (every line above the message table) is covered in the video.

LAYOUT. One 1920x1080 page: on the left a text panel for the 5.2 step, on the right the
console in an iframe at its own size, with "Made-up data, for demonstration" above it
for as long as it is on screen, and a caption below. Cards fill the screen and show no
console. Playwright records the whole page; the console is driven inside the frame.
"""

from __future__ import annotations

import argparse
import html
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Frame, Locator, Page, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import console_screenshots as shots  # noqa: E402  (also sets up the console's imports)

REPO = shots.REPO
YEAR = shots.YEAR
BASE = f"#/c/LUZON/{YEAR}"
WIDTH, HEIGHT = 1920, 1080
FRAME_W, FRAME_H = 1280, 864
# On the Failure page, every protocol file line above the message table (the line
# starting "Date") is covered: the header holds the campaign, user and server paths
# and the system pid of the captured failure. At least this many lines, or no video.
MIN_MASK_LINES = 20
# A scene's last caption holds for what is left of its time. A slow page load can use
# all of that, so it always gets at least this long.
MIN_LAST_CAPTION = 3.0

# The three results that may be stated, in these words (docs/SETTLED.md §2).
RESULTS = [
    "Production Bernese runs on gps3 have gone through the processing service since "
    "4 November 2026, started on the command line (bernese-run-year).",
    "LUZON January 2026: 31 of 31 days, in 53 minutes.",
    "PHREF 2025 reprocessed: all 360 planned days. Differences from the previous "
    "solutions come from the Bernese programs replaced in September.",
]


@dataclass
class Card:
    title: str
    lines: list[str]
    seconds: float
    note: str = ""
    dense: bool = False


@dataclass
class Scene:
    """One 5.2 step and what replaces it. ``left`` is (step, detail, section) from the
    work instruction, or None for something new; ``captions`` are shown in order."""

    title: str
    left: tuple[str, str, str] | None
    captions: list[str]
    seconds: float
    action: str


OPENING = Card(
    "The BSW console: what changes from 5.2",
    [
        "Bernese processing can now run on one Linux server, gps3, and the team follows "
        "it in a browser.",
        "The console's work instruction is still a draft.",
    ],
    9,
    note="Left: the 5.2 step. Right: the console.",
)

SCENES = [
    Scene(
        "Where it runs",
        (
            "Where Bernese runs",
            "Installed and run on each person's Windows PC.",
            "5.2 work instruction, section 5.1",
        ),
        [
            "One Linux server, gps3, runs Bernese 5.4. You follow it in a browser "
            "from any office PC.",
            "The header shows who is signed in, and whether the Bernese Processing "
            "Engine (BPE) is busy: the BPE lock.",
        ],
        10,
        "where",
    ),
    Scene(
        "Choosing a campaign",
        (
            "Choosing a campaign",
            "One campaign, for example PHIVOLCS, selected in the Bernese menu.",
            "5.2 work instruction, section 5.2.3",
        ),
        [
            "The maintainer sets up the campaigns. Pick one in the header.",
            "The Campaigns page shows each campaign's days, year by year: fixed, float, "
            "failed and not run, and its latest run.",
        ],
        10,
        "campaigns",
    ),
    Scene(
        "Seeing progress",
        (
            "Seeing what was processed",
            "Check the SAVEDISK outputs, looking through the folders with File "
            "Explorer and Notepad++.",
            "5.2 work instruction, section 5.5.5",
        ),
        [
            "The Calendar: one square per day, coloured fixed, float, failed, running, "
            "queued or not run.",
            "Pick a day to open its results, or to see why it failed.",
        ],
        10,
        "calendar",
    ),
    Scene(
        "Starting a run",
        (
            "Starting a run",
            "The RUNBPE 1 and 2 panels: the sessions, the script to start with, the "
            "scripts to skip.",
            "5.2 work instruction, section 5.6.1",
        ),
        [
            "Plan: choose the first and last day. The page checks the plan before "
            "anything runs: reference stations, products, and the steps of the process "
            "control file (PCF).",
            "Operators queue a check before the run starts (preflight). It runs only "
            "the plan's busiest day, the hardest one, so a setup error shows up early.",
            "Start stays off until the preflight for these days has finished. A run that "
            "skips steps or uses another PCF stays on the command line.",
        ],
        16,
        "plan",
    ),
    Scene(
        "When a run fails",
        (
            "When a run fails",
            "Open the log file, $YSS+0_$PID_$SUBID.LOG, in the BPE folder.",
            "5.2 work instruction, section 5.5.5",
        ),
        [
            "The Failure page names the failed step (PID 513), its script (HELMCHK) and "
            "its program (HELMR1).",
            "It shows the project's real known-errors entry: what the error means here, "
            "and what to check and change.",
            "Below, the step's own protocol file, a real captured failure, error line "
            "marked. Its header is covered in this video: it holds the server's paths.",
        ],
        15,
        "failure",
    ),
    Scene(
        "A run that keeps failing",
        None,
        [
            "The run stops itself: at once on a configuration error or one not on the "
            "known-errors list, after 3 identical failures in a row, or after 5 failed "
            "days in a row of any kind.",
            "Nothing is changed automatically. A person decides what happens next.",
        ],
        11,
        "runs",
    ),
    Scene(
        "Results",
        (
            "Final coordinates",
            "F1_$YSS+0.CRD, with a two-digit year: F1_251520.CRD.",
            "5.2 work instruction, section 5.5.5",
        ),
        [
            "5.4 writes FIN_ with a four-digit year: FIN_20251520.CRD. The Day page lists "
            "the day's seven results with their 5.2 names beside them.",
            "It also shows the stations in the solution, any dropped since the day "
            "before, and the HELMCHK RMS.",
        ],
        12,
        "day",
    ),
    Scene(
        "Outliers",
        (
            "Outlier removal",
            "Run outlier_input-site.py, right-click the outliers, edit the PLOT files "
            "by hand, run the MATLAB again.",
            "5.2 work instruction, section 6.3",
        ),
        [
            "The Time series page plots East, North and Up. Epochs the outlier rule "
            "flagged are orange.",
            "Click one to decide: confirm it, or keep it with a reason. Each decision is "
            "kept under the person's name, here 'demo'.",
            "No file is edited. Confirmed outliers change only a second fit, marked "
            "'not published'.",
        ],
        17,
        "outliers",
    ),
    Scene(
        "Reference station",
        (
            "Reference station",
            "Type the reference station, S01R, when plot_v2.py asks for it.",
            "5.2 work instruction, section 6.2.4",
        ),
        [
            "Choose the reference on a map or in a list: any station the campaign "
            "estimates. S01R is still available wherever it is estimated.",
            "A far-away reference tilts East, North and Up, so the page warns past "
            "5 degrees, and always shows the distance.",
        ],
        14,
        "reference",
    ),
]

CARDS = [
    Card(
        "What differs in the results",
        [
            "Frame and antenna model: IGS14 with I14 in 5.2, IGS20 with I20 on 5.4. "
            "I14 can't run on 5.4 at these dates.",
            "Orbits, clocks and Earth rotation: IGS finals in 5.2, CODE finals on 5.4.",
            "Results are not directly comparable with 5.2.",
        ],
        8,
    ),
    Card(
        "What stays the same",
        [
            "Raw data to RINEX still follows the 5.2 work instruction (section 4).",
            "Bernese's own programs still do the computation.",
            "Published velocities still come from the MATLAB.",
            "The judgement steps stay with people.",
        ],
        8,
    ),
    Card("Results so far", RESULTS, 8, note="Real results from gps3."),
    Card(
        "Not built yet",
        [
            "Listing queued requests in the console.",
            "Editing station files, adding a site, using a result as a priori, "
            "checking an ocean-loading (BLQ) reply.",
            "The age of the GEN folder against AIUB's.",
            "Confirmed outliers leaving the published fit: waiting on the team's decision.",
            "The ambiguity fixing rate on the Day page.",
            'Showing days left out of a run on purpose as "excluded".',
            "A run with skipped steps, another RNXGRA setting or another PCF stays on the "
            "command line, with the maintainer.",
        ],
        12,
        dense=True,
    ),
    Card(
        "Still open",
        [
            "How the IGS14/I14 and IGS20/I20 series join.",
            "Whether confirmed outliers leave the published fit.",
        ],
        8,
    ),
    Card(
        "What we need from the team",
        [
            "Review the draft work instruction for the console "
            "(docs/bsw_console_work_instruction.md).",
            "Answer its section 9 questions.",
        ],
        7,
    ),
]

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
:root { --ink:#1c2321; --muted:#596260; --panel:#ebe7df; --bar:#253642; --amber:#f2b33d; }
* { box-sizing:border-box; }
body { margin:0; width:1920px; height:1080px; overflow:hidden; color:var(--ink);
  background:#f6f4ef; font-family:"Noto Sans","Ubuntu Sans","DejaVu Sans",sans-serif; }
#scene { display:grid; grid-template-columns:640px 1280px; height:1080px; }
#left { background:var(--panel); padding:56px 48px 48px; display:flex; flex-direction:column;
  border-right:4px solid #cbc3b5; }
#left .tag { font-size:30px; font-weight:700; letter-spacing:.04em; color:var(--muted); }
#left h2 { font-size:42px; line-height:1.2; margin:30px 0 22px; }
#left p { font-size:32px; line-height:1.4; margin:0; }
#left .sec { margin-top:auto; font-size:27px; color:var(--muted); }
#left.new h2 { font-size:56px; }
#right { display:flex; flex-direction:column; }
#bar { height:56px; background:var(--bar); color:#fff; display:flex; align-items:center;
  justify-content:space-between; padding:0 20px; font-size:27px; font-weight:700; }
#badge { background:var(--amber); color:#1c1c1c; font-size:23px; font-weight:700;
  padding:5px 14px; border-radius:6px; }
iframe { width:1280px; height:864px; border:0; display:block; background:#fff; }
#cap { height:160px; background:#151a1d; color:#fff; font-size:30px; line-height:1.32;
  padding:16px 28px; display:flex; align-items:center; }
#card { position:fixed; inset:0; background:#f6f4ef; display:none; padding:84px 140px; }
#card h1 { font-size:58px; line-height:1.15; margin:0 0 44px; }
#card ul { margin:0; padding-left:1.1em; }
#card li { font-size:36px; line-height:1.4; margin:0 0 20px; }
#card.dense li { font-size:31px; margin-bottom:14px; }
#card .note { position:absolute; bottom:56px; left:140px; right:140px; font-size:27px;
  color:var(--muted); }
#ring { position:fixed; border:5px solid var(--amber); border-radius:10px; display:none;
  pointer-events:none; }
#cover { position:fixed; left:640px; top:56px; width:1280px; height:864px;
  background:#f3f2ee; display:none; }
.mask { position:fixed; background:#3d4346; color:#fff; font-size:21px; display:flex;
  align-items:center; justify-content:center; text-align:center; pointer-events:none; }
</style></head><body>
<div id="scene"><div id="left"></div><div id="right">
<div id="bar"><span>Console on 5.4</span><span id="badge">Made-up data, for demonstration</span></div>
<iframe name="console" src="about:blank"></iframe><div id="cap"></div></div></div>
<div id="cover"></div><div id="card"></div><div id="ring"></div>
<script>
window.showCard = (title, lines, note, dense) => {
  const c = document.getElementById('card');
  c.className = dense ? 'dense' : '';
  c.innerHTML = '<h1>' + title + '</h1><ul>' + lines.map(l => '<li>' + l + '</li>').join('')
    + '</ul>' + (note ? '<div class="note">' + note + '</div>' : '');
  c.style.display = 'block';
};
window.showScene = (leftHtml, isNew) => {
  const l = document.getElementById('left');
  l.className = isNew ? 'new' : ''; l.innerHTML = leftHtml;
  document.getElementById('card').style.display = 'none';
};
window.cover = (on) => { document.getElementById('cover').style.display = on ? 'block' : 'none'; };
window.caption = (text) => { document.getElementById('cap').innerHTML = text; };
window.ring = (b) => {
  const r = document.getElementById('ring');
  if (!b) { r.style.display = 'none'; return; }
  Object.assign(r.style, {display:'block', left:(b.x-8)+'px', top:(b.y-8)+'px',
    width:(b.width+16)+'px', height:(b.height+16)+'px'});
};
window.masks = (boxes, text) => {
  document.querySelectorAll('.mask').forEach(m => m.remove());
  for (const b of boxes) {
    const m = document.createElement('div'); m.className = 'mask'; m.textContent = text;
    Object.assign(m.style, {left:b.x+'px', top:b.y+'px', width:b.width+'px', height:b.height+'px'});
    document.body.appendChild(m);
  }
};
</script></body></html>"""


class Show:
    """The wrapper page, the console frame in it, and the timeline for the captions."""

    def __init__(self, page: Page, url: str) -> None:
        self.page, self.url = page, url
        self.cues: list[tuple[float, str]] = []
        self.t0 = time.monotonic()
        page.set_content(PAGE)
        self.frame: Frame = page.frame(name="console")

    def now(self) -> float:
        return time.monotonic() - self.t0

    def cue(self, text: str) -> None:
        self.cues.append((self.now(), text))

    def card(self, card: Card) -> None:
        self.page.evaluate(
            "([t, l, n, d]) => showCard(t, l, n, d)",
            [
                html.escape(card.title),
                [html.escape(x) for x in card.lines],
                html.escape(card.note),
                card.dense,
            ],
        )
        self.cue("\n".join([card.title, *card.lines, *([card.note] if card.note else [])]))
        self.page.wait_for_timeout(card.seconds * 1000)

    def scene(self, scene: Scene) -> None:
        start = self.now()
        if scene.left:
            step, detail, section = (html.escape(x) for x in scene.left)
            left = (
                f'<div class="tag">BSW 5.2</div><h2>{step}</h2><p>{detail}</p>'
                f'<div class="sec">{section}</div>'
            )
        else:
            left = '<div class="tag">BSW 5.2</div><h2>New</h2>'
        # Masks stay until the next page load covers the console (open): taking them
        # off first would show what they hide for a frame.
        self.ring(None)
        self.page.evaluate("() => caption('')")
        self.page.evaluate("([l, n]) => showScene(l, n)", [left, scene.left is None])
        getattr(self, f"do_{scene.action}")(scene)
        rest = scene.seconds - (self.now() - start)
        self.page.wait_for_timeout(max(rest, MIN_LAST_CAPTION) * 1000)
        self.ring(None)

    def say(self, scene: Scene, i: int, hold: float = 0.0) -> None:
        """Show caption i, then hold it for ``hold`` seconds."""
        text = scene.captions[i]
        self.page.evaluate("t => caption(t)", html.escape(text))
        left = (
            f"BSW 5.2: {scene.left[0]}. "
            if (i == 0 and scene.left)
            else ("BSW 5.2: new. " if i == 0 else "")
        )
        self.cue(f"{left}Console on 5.4: {text}")
        if hold:
            self.page.wait_for_timeout(hold * 1000)

    def ring(self, target: Locator | None) -> None:
        box = target.bounding_box() if target is not None else None
        self.page.evaluate("b => ring(b)", box)

    def masks(self, boxes: list[dict], text: str = "") -> None:
        self.page.evaluate("([b, t]) => masks(b, t)", [boxes, text])

    def open(self, route: str, wait_for: str, before_reveal=None) -> None:
        """Load a page with the console covered, so neither the page before it nor a
        half-drawn one shows; ``before_reveal`` runs while it is still covered."""
        self.page.evaluate("() => cover(true)")
        self.masks([])
        shots.open_route(self.frame, self.url, route)
        self.frame.get_by_text(wait_for).first.wait_for(timeout=20000)
        self.frame.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(300)
        if before_reveal:
            before_reveal()
        self.page.evaluate("() => cover(false)")

    def scroll_to(self, target: Locator, offset: int = 16) -> None:
        """Scroll the console so ``target`` sits ``offset`` px below the frame's top."""
        target.evaluate(
            "(el, off) => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - off)",
            offset,
        )
        self.page.wait_for_timeout(400)

    # --- the scenes ------------------------------------------------------------------

    def do_where(self, s: Scene) -> None:
        self.open("#/", "Recent activity")
        self.ring(self.frame.locator(".brand"))
        self.say(s, 0, 5)
        self.ring(self.frame.locator("header .lockpill").last)
        self.say(s, 1)

    def do_campaigns(self, s: Scene) -> None:
        self.ring(self.frame.locator("header select").first)
        self.say(s, 0, 4)
        self.ring(self.frame.locator("main table").first)
        self.say(s, 1)

    def do_calendar(self, s: Scene) -> None:
        self.open(BASE, "Fixed")
        self.say(s, 0, 5)
        self.frame.locator('[aria-label*="DOY 036"]').first.click()
        self.page.wait_for_timeout(400)
        self.ring(self.frame.get_by_text("Open this day").first)
        self.say(s, 1)

    def do_plan(self, s: Scene) -> None:
        self.open(f"{BASE}/plan?from=35&to=40", "Checks before the run")
        self.ring(self.frame.get_by_text("Checks before the run").locator(".."))
        self.say(s, 0, 6)
        button = self.frame.get_by_role("button", name="Queue preflight")
        self.ring(button)
        self.say(s, 1, 1.8)
        button.click()
        self.frame.get_by_text("Preflight queued").wait_for(timeout=20000)
        self.page.wait_for_timeout(2500)
        self.ring(self.frame.get_by_role("button", name="Start", exact=True))
        self.say(s, 2)

    def failure_masks(self) -> None:
        """Cover the protocol file's header, every line above the message table,
        wherever it is on screen. Stops the recording if the table isn't found."""
        frame_box = self.page.locator("iframe").bounding_box()
        viewer = self.frame.locator(".viewer").first.bounding_box()
        lines = self.frame.locator(".viewer .ln")
        texts = self.frame.locator(".viewer .ln > span:last-child").all_inner_texts()
        table = next((i for i, t in enumerate(texts) if t.strip().startswith("Date")), None)
        if table is None or table < MIN_MASK_LINES:
            raise SystemExit("the protocol file's header was not found: nothing to cover")
        first = lines.nth(0).bounding_box()
        last = lines.nth(table - 1).bounding_box()
        top = max(first["y"], viewer["y"], frame_box["y"])
        bottom = min(
            last["y"] + last["height"],
            viewer["y"] + viewer["height"],
            frame_box["y"] + frame_box["height"],
        )
        boxes = []
        if bottom > top:
            boxes.append(
                {"x": viewer["x"], "y": top, "width": viewer["width"], "height": bottom - top}
            )
        self.masks(boxes, "Header lines covered in this video: they hold the server's paths")

    def do_failure(self, s: Scene) -> None:
        self.open(f"{BASE}/day/36/failure", "PID and script", before_reveal=self.failure_masks)
        self.ring(self.frame.get_by_text("What failed").locator(".."))
        self.say(s, 0, 4.5)
        self.ring(self.frame.get_by_text("Known-errors list").locator(".."))
        self.say(s, 1, 4)
        self.ring(None)
        # Moving the file: cover the console, scroll, mask the header, uncover.
        self.page.evaluate("() => cover(true)")
        self.scroll_to(self.frame.locator(".viewer").first, 80)
        self.frame.locator(".viewer").first.evaluate("el => el.scrollTop = el.scrollHeight")
        self.page.wait_for_timeout(300)
        self.failure_masks()
        self.page.evaluate("() => cover(false)")
        self.ring(self.frame.locator(".viewer .ln").nth(27))
        self.say(s, 2)

    def do_runs(self, s: Scene) -> None:
        self.open(f"{BASE}/run", "solved")
        self.ring(self.frame.locator(".banner.warn").first)
        self.say(s, 0, 6)
        self.ring(self.frame.get_by_text("Identical failures in a row").locator("..").locator(".."))
        self.say(s, 1)

    def do_day(self, s: Scene) -> None:
        self.open(f"{BASE}/day/35", "HELMCHK RMS")
        table = self.frame.get_by_text("Results in SAVEDISK").first
        self.scroll_to(table, 12)
        self.ring(self.frame.locator("td", has_text="F1_250350.CRD").first.locator(".."))
        self.say(s, 0, 6)
        self.frame.evaluate("window.scrollTo(0, 0)")
        self.page.wait_for_timeout(400)
        self.ring(self.frame.get_by_text("Quality", exact=True).locator(".."))
        self.say(s, 1)

    def click_epoch(self, year: int, doy: int) -> None:
        """The epoch at ``year``-``doy`` on the plot. The year button shows one year
        across the panel, and a click picks the nearest epoch (as in console_screenshots)."""
        self.frame.get_by_role("button", name=str(year), exact=True).click()
        self.page.wait_for_timeout(500)
        box = self.frame.locator(".u-over").first.bounding_box()
        epoch = f"{year}-{doy:03d}"
        middle = box["x"] + box["width"] * (doy - 1) / 365.0
        for dx in (0, 1, -1, 2, -2, 3, -3, 4, -4):
            self.page.mouse.move(middle + dx, box["y"] + box["height"] / 2)
            self.page.wait_for_timeout(100)
            self.page.mouse.click(middle + dx, box["y"] + box["height"] / 2)
            self.frame.locator("#ts-decide").wait_for(timeout=20000)
            if epoch in self.frame.locator("#ts-decide").inner_text():
                return
        raise SystemExit(f"could not click {epoch}")

    def do_outliers(self, s: Scene) -> None:
        self.open(f"{BASE}/time-series", "Reference station")
        shots.pick_station(self.frame, "SYN1")
        plot = self.frame.locator("[data-testid=ts-plot]")
        plot.locator("canvas").first.wait_for(timeout=20000)
        self.frame.wait_for_load_state("networkidle")
        self.scroll_to(plot, 60)
        self.say(s, 0, 4)
        self.click_epoch(*shots.SPIKE)
        confirm = self.frame.get_by_role("button", name="Confirm outlier")
        confirm.wait_for(timeout=20000)
        self.ring(self.frame.locator("#ts-decide"))
        self.say(s, 1, 5)
        confirm.click()
        self.ring(None)  # the popup it was on closes
        # The velocity table's row; the plot's hidden legend has a row with the same words.
        row = self.frame.locator('th[scope="row"]', has_text="not published").first.locator("..")
        row.wait_for(timeout=20000)
        self.scroll_to(self.frame.get_by_text("recorded as outlier by").first, 200)
        self.ring(row)
        self.say(s, 2)

    def do_reference(self, s: Scene) -> None:
        self.ring(None)
        shots.pick_station(self.frame, "SYN5")
        panel = self.frame.get_by_role("region", name="Map of the stations")
        self.frame.locator("[data-testid=ts-plot] canvas").first.wait_for(timeout=20000)
        self.frame.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(500)
        self.scroll_to(panel, 20)
        self.page.wait_for_timeout(600)  # the map's move to its opening view is animated
        self.ring(self.frame.locator("label", has_text="Reference station").locator("select"))
        self.say(s, 0, 6)
        self.ring(None)
        self.frame.locator("label", has_text="Reference station").locator("select").select_option(
            "FAR1"
        )
        panel.get_by_role("button", name="All stations").click()
        banner = self.frame.locator(".banner.warn").first
        banner.wait_for(timeout=20000)
        self.frame.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(500)
        self.scroll_to(banner, 520)
        self.ring(banner)
        self.say(s, 1)


def srt(cues: list[tuple[float, str]], end: float, offset: float) -> str:
    def stamp(t: float) -> str:
        ms = max(0, round((t - offset) * 1000))
        h, ms = divmod(ms, 3_600_000)
        m, ms = divmod(ms, 60_000)
        sec, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"

    out = []
    for i, (t, text) in enumerate(cues):
        nxt = cues[i + 1][0] if i + 1 < len(cues) else end
        out.append(f"{i + 1}\n{stamp(t)} --> {stamp(nxt)}\n{text}\n")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=Path.home() / "bsw-console-demo")
    args = ap.parse_args()
    out = args.out.expanduser().resolve()
    if out == REPO or REPO in out.parents:
        raise SystemExit(f"--out must be outside the repository, not {out}")
    scratch = shots.SCRATCH.resolve()  # emptied at the start and removed at the end
    if out == scratch or scratch in out.parents:
        raise SystemExit(f"--out must be outside the scratch folder, not {out}")
    out.mkdir(parents=True, exist_ok=True)
    raw = Path(tempfile.mkdtemp(prefix="bsw-console-demo-video-"))

    worker = server = None
    try:
        s = shots.settings()
        worker = shots.pretend_worker(s)
        url, server = shots.serve(s)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(
                viewport={"width": WIDTH, "height": HEIGHT},
                record_video_dir=str(raw),
                record_video_size={"width": WIDTH, "height": HEIGHT},
                color_scheme="light",
                extra_http_headers={"X-Remote-User": shots.USER},
            )
            page = context.new_page()  # the recording starts with the page
            opened = time.monotonic()
            show = Show(page, url)
            show.t0 = opened
            # The opening card first, then load the console behind it, so the first
            # scene starts drawn. Everything before the card is cut (offset).
            show.page.evaluate("() => showCard('', [], '', false)")
            show.open("#/", "Recent activity")
            offset = show.now()
            show.card(OPENING)
            for scene in SCENES:
                show.scene(scene)
            for card in CARDS:
                show.card(card)
            end = show.now()
            video = page.video
            context.close()
            browser.close()
            webm = out / "demo.webm"
            shutil.move(video.path(), webm)
    finally:
        if server:
            server.should_exit = True
        if worker:
            worker.close()
        shutil.rmtree(shots.SCRATCH, ignore_errors=True)
        shutil.rmtree(raw, ignore_errors=True)

    (out / "demo.srt").write_text(srt(show.cues, end, offset), encoding="utf-8")
    (out / "timeline.json").write_text(
        json.dumps({"offset": offset, "end": end, "cues": show.cues}, indent=1), encoding="utf-8"
    )
    mp4 = out / "demo.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{offset:.2f}",
        "-t",
        f"{end - offset:.2f}",
        "-i",
        str(webm),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
        "-crf",
        "18",
        "-an",
        str(mp4),
    ]
    # Playwright's own ffmpeg, for one, has no libx264. The webm and srt are safe by now.
    if shutil.which("ffmpeg") and subprocess.run(cmd, check=False).returncode == 0:
        print(mp4)
    else:
        print("no ffmpeg with libx264 on PATH; convert with:\n  " + shlex.join(cmd))
    print(f"{webm}\n{out / 'demo.srt'}\nlength {end - offset:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
