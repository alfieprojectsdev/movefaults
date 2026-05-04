#!/usr/bin/env bash
# VADASE RT-Monitor — Demo setup and launcher
# Replays the BOST Mw ~7.6 (Dec 2023) earthquake dataset at 1 Hz.
# Requires: Python 3.11+, internet access (first run only for uv/dep install).
# No database required — all output goes to the console.

set -euo pipefail

# Optional: --speed N  (default 8 → event reached in ~4.6 min instead of 37)
SPEED=8
while [[ $# -gt 0 ]]; do
    case "$1" in
        --speed) SPEED="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SERVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
BOST_DATA="data/NMEA_BOST LDM_20231202_140000"

# ── 0. Python 3.11+ check ─────────────────────────────────────────────────────
PYTHON="$(command -v python3 || command -v python || true)"
if [[ -z "$PYTHON" ]]; then
    echo "ERROR: Python not found. Install Python 3.11+ from https://python.org and re-run."
    exit 1
fi

PY_VERSION="$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_MAJOR="${PY_VERSION%%.*}"
PY_MINOR="${PY_VERSION#*.}"

if [[ "$PY_MAJOR" -lt 3 || ( "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11 ) ]]; then
    echo "ERROR: Python 3.11+ required (found $PY_VERSION)."
    echo "  Download: https://python.org/downloads"
    exit 1
fi

echo "Python $PY_VERSION  ✓"

# ── 1. Ensure uv is available ─────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    echo "uv not found — installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "uv $(uv --version)"

# ── 2. Optional: live matplotlib plot ─────────────────────────────────────────
PLOT_FLAG=""
if cd "$REPO_ROOT" && uv run --extra vadase-rt-monitor python -c "import matplotlib" &>/dev/null 2>&1; then
    PLOT_FLAG="--plot"
    echo "matplotlib detected — live ENU plot enabled."
else
    echo "matplotlib not found — running without live plot."
    echo "  To enable: uv pip install matplotlib  (then re-run this script)"
fi

# ── 3. Run ────────────────────────────────────────────────────────────────────
echo ""
APPROX_MINS=$(echo "scale=1; 37 / $SPEED" | bc)
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
    $PLOT_FLAG
