"""
CLI entry point for the velocity-reviewer tool.

Usage:
    uv run velocity-reviewer --plots-dir /path/to/PLOTS
    uv run velocity-reviewer --plots-dir /path/to/PLOTS --port 8765
"""

import argparse
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="velocity-reviewer",
        description=(
            "Web-based GNSS time series outlier reviewer. "
            "Replaces the interactive matplotlib outlier_input-site.py GUI. "
            "Opens a browser at http://localhost:<port> for point-click outlier selection."
        ),
    )
    parser.add_argument(
        "--plots-dir",
        required=True,
        type=Path,
        metavar="DIR",
        help="Path to the PLOTS directory containing a '123' site list and PLOT files.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        metavar="PORT",
        help="Local port for the web server (default: 8765).",
    )
    args = parser.parse_args()

    plots_dir = args.plots_dir.resolve()
    if not plots_dir.is_dir():
        print(f"Error: '{plots_dir}' is not a directory.", file=sys.stderr)
        sys.exit(1)
    if not (plots_dir / "123").exists():
        print(
            f"Error: no '123' site list file found in '{plots_dir}'.\n"
            "The PLOTS directory must contain a '123' file listing site codes.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Inject plots dir into the FastAPI app via environment variable.
    os.environ["VELOCITY_REVIEWER_PLOTS_DIR"] = str(plots_dir)

    url = f"http://localhost:{args.port}"
    print(f"\nVelocity Reviewer")
    print(f"  Plots directory : {plots_dir}")
    print(f"  Address         : {url}")
    print(f"\nPress Ctrl+C to stop.\n")

    def _open_browser() -> None:
        time.sleep(1.2)
        webbrowser.open(url)

    threading.Thread(target=_open_browser, daemon=True).start()

    # Import here so uvicorn is only needed when the tool actually runs.
    import uvicorn

    uvicorn.run(
        "velocity_reviewer.app:app",
        host="127.0.0.1",
        port=args.port,
        log_level="warning",
    )
