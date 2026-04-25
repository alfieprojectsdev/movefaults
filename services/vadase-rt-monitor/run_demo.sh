#!/usr/bin/env bash
# VADASE RT-Monitor — Demo setup and launcher
# Replays the BOST Mw ~7.6 (Dec 2023) earthquake dataset at 1 Hz.
# Requires: Python 3.11+, internet access (first run only for uv/dep install).
# No database required — all output goes to the console.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SERVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
BOST_DATA="data/NMEA_BOST LDM_20231202_140000"

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
echo "Starting BOST replay (1 Hz, Ctrl-C to stop)..."
echo ""

cd "$SERVICE_DIR"
PYTHONPATH=. uv run --extra vadase-rt-monitor python scripts/replay_events.py \
    --file "$BOST_DATA" \
    --mode replay \
    --station BOST \
    --base-date 2023-12-02 \
    --dry-run \
    --pattern "*.rtl" \
    $PLOT_FLAG
