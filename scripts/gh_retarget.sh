#!/usr/bin/env bash
# gh_retarget.sh — change a PR's base branch (gated-write bypass).
# Usage: scripts/gh_retarget.sh <pr-number> <new-base>
set -euo pipefail
gh pr edit "${1:?pr}" --base "${2:?base}"
