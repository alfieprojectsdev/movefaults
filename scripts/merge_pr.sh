#!/usr/bin/env bash
# merge_pr.sh — merge a GitHub PR (gated-write bypass; see open_pr.sh).
# Usage: scripts/merge_pr.sh <pr-number> [--squash|--merge] [--delete-branch]
set -euo pipefail
PR="${1:?pr number required}"; shift || true
METHOD="--merge"; DELETE=""
while [ $# -gt 0 ]; do case "$1" in
  --squash) METHOD="--squash";;
  --merge)  METHOD="--merge";;
  --delete-branch) DELETE="--delete-branch";;
  *) echo "unknown arg: $1" >&2; exit 2;;
esac; shift; done
gh pr merge "$PR" $METHOD $DELETE
