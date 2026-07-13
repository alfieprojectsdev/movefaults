#!/usr/bin/env bash
# VADASE RT-Monitor — Demo setup and launcher
# Replays the BOST Mw ~7.6 (Dec 2023) earthquake dataset at 1 Hz.
# Requires: Python 3.11+, internet access (first run only for uv/dep install).
# No database required — all output goes to the console.

set -euo pipefail

usage() {
    cat <<'USAGE'
Usage: ./run_demo.sh [--speed N] [--help]

Replays the BOST station Dec 2, 2023 Mw 7.6 Mindanao earthquake at 1 Hz
with live event detection. No database required.

Options:
  --speed N   Playback speed multiplier (default 8 → event reached in
              ~4.6 min instead of ~37 min real time)
  --help      Show this help and exit

Prerequisites: Python 3.11+ and internet access (first run installs uv
and dependencies). The BOST dataset must exist at:
  data/NMEA_BOST LDM_20231202_140000/
USAGE
}

# Optional: --speed N  (default 8 → event reached in ~4.6 min instead of 37)
SPEED=8
while [[ $# -gt 0 ]]; do
    case "$1" in
        --speed) SPEED="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1"; usage; exit 1 ;;
    esac
done

if [[ ! "$SPEED" =~ ^[0-9]+$ || "$SPEED" -lt 1 ]]; then
    echo "ERROR: --speed must be a positive integer (got '$SPEED')."
    exit 1
fi

SERVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
BOST_DATA="data/NMEA_BOST LDM_20231202_140000"

# ── 0. Dataset check ──────────────────────────────────────────────────────────
# The BOST dataset is not committed to the repository (raw field data).
if [[ ! -d "$SERVICE_DIR/$BOST_DATA" ]]; then
    echo "ERROR: demo dataset not found: $SERVICE_DIR/$BOST_DATA"
    echo "  This dataset is not in git. Copy it from the project data store"
    echo "  (services/vadase-rt-monitor/data/ on the R740, or ask the MOVE"
    echo "  Faults data manager) before running the demo."
    exit 1
fi

# ── 1. Python 3.11+ check ─────────────────────────────────────────────────────
# uv provisions its own Python, but fail early with a clear message if the
# machine has none at all.
PYTHON="$(command -v python3 || command -v python || true)"
if [[ -z "$PYTHON" ]]; then
    echo "ERROR: Python not found. Install Python 3.11+ from https://python.org and re-run."
    exit 1
fi

if ! "$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    PY_VERSION="$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    echo "ERROR: Python 3.11+ required (found $PY_VERSION)."
    echo "  Download: https://python.org/downloads"
    exit 1
fi

echo "Python $("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')  ✓"

# ── 2. Ensure uv is available ─────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    echo "uv not found — installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "uv $(uv --version)"

# ── 3. Run ────────────────────────────────────────────────────────────────────
# --plot is always passed: replay_events.py degrades gracefully (prints a
# notice and continues) when matplotlib isn't installed.
echo ""
APPROX_MINS=$(( (37 + SPEED - 1) / SPEED ))
echo "Replaying BOST station — Dec 2, 2023 Mw 7.6 Mindanao earthquake"
echo "Threshold: 15 mm/s horizontal velocity  |  Event onset: ~14:37:26 UTC"
echo "Playback speed: ${SPEED}×  (event reached in ~${APPROX_MINS} min)"
echo ""

cd "$SERVICE_DIR"
PYTHONPATH=. uv run --extra vadase-rt-monitor python scripts/replay_events.py \
    --file "$BOST_DATA" \
    --mode replay \
    --speed "$SPEED" \
    --station BOST \
    --base-date 2023-12-02 \
    --dry-run \
    --quiet \
    --pattern "*.rtl" \
    --plot
