#!/bin/bash
#
# This script reorganizes legacy analysis scripts from the movefaults repository
# into their more relevant project repositories (drive-archaeologist and vadase-rt-monitor).
#

set -e

# --- Configuration ---
SOURCE_BASE_DIR="/home/finch/repos/movefaults/analysis"
ARCHAEOLOGIST_DIR="/home/finch/repos/drive-archaeologist"
VADASE_DIR="/home/finch/repos/vadase-rt-monitor"

# --- Main Logic ---

echo "Starting file reorganization..."

# 1. Define destination subdirectories for legacy material
ARCHAEOLOGIST_DEST="$ARCHAEOLOGIST_DIR/reference_scripts"
VADASE_DEST="$VADASE_DIR/reference_scripts"

echo "Creating destination directories (if they don't exist)..."
mkdir -p "$ARCHAEOLOGIST_DEST"
mkdir -p "$VADASE_DEST"

# 2. Move files related to initial data checking and conversion to drive-archaeologist
echo "Moving '05 Single Frequency' to $ARCHAEOLOGIST_DEST..."
mv "$SOURCE_BASE_DIR/05 Single Frequency" "$ARCHAEOLOGIST_DEST/"

echo "Moving '10 RINEX Checker' to $ARCHAEOLOGIST_DEST..."
mv "$SOURCE_BASE_DIR/10 RINEX Checker" "$ARCHAEOLOGIST_DEST/"

# 3. Move files related to real-time VADASE NMEA data to vadase-rt-monitor
echo "Moving '07 Sample time series from NMEA' to $VADASE_DEST..."
mv "$SOURCE_BASE_DIR/07 Sample time series from NMEA" "$VADASE_DEST/"

echo ""
echo "File reorganization complete."
echo "The following directories have been moved:"
echo "  - To drive-archaeologist/reference_scripts/:"
echo "    - 05 Single Frequency"
echo "    - 10 RINEX Checker"
echo "  - To vadase-rt-monitor/reference_scripts/:"
echo "    - 07 Sample time series from NMEA"
