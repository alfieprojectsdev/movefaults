"""
FastAPI application for the web-based GNSS time series outlier reviewer.

Single-session: state is held in module-level dicts.
The plots directory is injected via the VELOCITY_REVIEWER_PLOTS_DIR env var,
set by cli.py before uvicorn starts.
"""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from velocity_reviewer.reader import read_123, read_offsets, read_plot, write_outliers_txt
from velocity_reviewer.regression import process_site

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Velocity Reviewer", docs_url=None, redoc_url=None)

# ── Session state (module-level; single-session tool) ────────────────────────
_plots_dir: Path | None = None
_sites: list[str] = []
_selections: dict[str, list[float]] = {}   # site → timestamps chosen for output
_done: set[str] = set()                     # sites accepted by operator
# ─────────────────────────────────────────────────────────────────────────────


def _get_plots_dir() -> Path:
    global _plots_dir, _sites
    if _plots_dir is None:
        raw = os.environ.get("VELOCITY_REVIEWER_PLOTS_DIR")
        if not raw:
            raise RuntimeError("VELOCITY_REVIEWER_PLOTS_DIR not set")
        _plots_dir = Path(raw)
        _sites = read_123(_plots_dir)
    return _plots_dir


# ── Routes ────────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=(STATIC_DIR / "index.html").read_text())


@app.get("/api/sites")
async def list_sites():
    _get_plots_dir()
    return {
        "sites": _sites,
        "done": sorted(_done),
        "total": len(_sites),
    }


@app.get("/api/sites/{site}/data")
async def site_data(site: str):
    site = site.upper()
    plots_dir = _get_plots_dir()

    if site not in _sites:
        raise HTTPException(404, f"Site '{site}' not in 123 file")

    plot_path = plots_dir / site
    if not plot_path.exists():
        raise HTTPException(404, f"PLOT file for '{site}' not found in {plots_dir}")

    t, e, n, u = read_plot(plots_dir, site)
    data = process_site(t, e, n, u)

    all_offsets = read_offsets(plots_dir)
    data["offsets"] = [
        {"year": yr, "type": tag} for yr, tag in all_offsets.get(site, [])
    ]

    # Return any previously saved selection for this site (supports Prev navigation)
    data["current_selection"] = _selections.get(site, [])
    return data


@app.get("/api/sites/{site}/outliers")
async def get_outliers(site: str):
    return {"timestamps": _selections.get(site.upper(), [])}


@app.post("/api/sites/{site}/outliers")
async def set_outliers(site: str, body: dict):
    """Live-update the selection as the operator clicks points."""
    site = site.upper()
    _selections[site] = [float(ts) for ts in body.get("timestamps", [])]
    return {"ok": True, "count": len(_selections[site])}


@app.post("/api/sites/{site}/accept")
async def accept_site(site: str, body: dict):
    """Finalise selection for this site and mark it done."""
    site = site.upper()
    _selections[site] = [float(ts) for ts in body.get("timestamps", [])]
    _done.add(site)
    return {"ok": True, "done_count": len(_done), "total": len(_sites)}


@app.post("/api/export")
async def export_outliers():
    """Write OUTLIERS.txt to the plots directory."""
    plots_dir = _get_plots_dir()
    out_path = write_outliers_txt(plots_dir, _selections)
    total = sum(len(v) for v in _selections.values())
    return {"path": str(out_path), "total_outliers": total}
