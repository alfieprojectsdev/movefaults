#!/usr/bin/env bash
# git_merge_main.sh — merge origin/main into the current branch (gated-write bypass).
# On conflict, leaves the tree in a merging state for manual resolution.
set -uo pipefail
git merge origin/main --no-edit
