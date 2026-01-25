#!/bin/bash
#
# This script recovers the project files that were moved to /tmp
# by the previous buggy migration script.
#

set -e

# --- Configuration ---
MONOREPO_ROOT="/home/finch/repos/movefaults"
RECOVERED_VADASE_PATH="/tmp/tmp.m6UHKlbPWo"
RECOVERED_ARCHAEOLOGIST_PATH="/tmp/tmp.FCWm9KPzuY"

VADASE_DEST_DIR="${MONOREPO_ROOT}/services"
ARCHAEOLOGIST_DEST_DIR="${MONOREPO_ROOT}/tools"

FINAL_VADASE_PATH="${VADASE_DEST_DIR}/vadase-rt-monitor"
FINAL_ARCHAEOLOGIST_PATH="${ARCHAEOLOGIST_DEST_DIR}/drive-archaeologist"

echo "--- Starting Recovery ---"

# 1. Ensure the destination base directories exist
mkdir -p "$VADASE_DEST_DIR"
mkdir -p "$ARCHAEOLOGIST_DEST_DIR"
echo "Created services/ and tools/ directories in movefaults."

# 2. Move the recovered directories to their final destinations
echo "Moving VADASE-RT Monitor files to: ${FINAL_VADASE_PATH}"
mv "$RECOVERED_VADASE_PATH" "$FINAL_VADASE_PATH"

echo "Moving Drive Archaeologist files to: ${FINAL_ARCHAEOLOGIST_PATH}"
mv "$RECOVERED_ARCHAEOLOGIST_PATH" "$FINAL_ARCHAEOLOGIST_PATH"

echo ""
echo "--- RECOVERY COMPLETE ---"
echo "Your files have been successfully recovered and moved into the monorepo structure."
echo "You can now safely proceed with the next steps of the migration (like unifying configuration)."
