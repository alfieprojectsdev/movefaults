#!/usr/bin/env bash
# open_pr.sh — open (or report) a GitHub pull request for a branch.
#
# Reusable helper for the PR-per-major-commit workflow. Idempotent: if a PR for
# the head branch already exists, it prints the existing URL and exits 0 instead
# of erroring. Pushes the head branch first (with upstream) when needed.
#
# Usage:
#   scripts/open_pr.sh --base main --title "..." --body-file BODY.md [--head BRANCH] [--draft]
#
# Defaults: --head = current branch. Requires: gh (authenticated), git.
set -euo pipefail

BASE=""
HEAD=""
TITLE=""
BODY_FILE=""
DRAFT=""

while [ $# -gt 0 ]; do
  case "$1" in
    --base)      BASE="$2"; shift 2 ;;
    --head)      HEAD="$2"; shift 2 ;;
    --title)     TITLE="$2"; shift 2 ;;
    --body-file) BODY_FILE="$2"; shift 2 ;;
    --draft)     DRAFT="--draft"; shift ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

[ -n "$BASE" ]      || { echo "FATAL: --base required" >&2; exit 2; }
[ -n "$TITLE" ]     || { echo "FATAL: --title required" >&2; exit 2; }
[ -n "$BODY_FILE" ] || { echo "FATAL: --body-file required" >&2; exit 2; }
[ -f "$BODY_FILE" ] || { echo "FATAL: body file not found: $BODY_FILE" >&2; exit 2; }

# Default head to the current branch.
if [ -z "$HEAD" ]; then
  HEAD="$(git rev-parse --abbrev-ref HEAD)"
fi
echo "PR: $HEAD -> $BASE"

# Push the head branch (idempotent; sets upstream on first push).
if ! git rev-parse --abbrev-ref --symbolic-full-name "@{u}" >/dev/null 2>&1; then
  echo "  pushing $HEAD with --set-upstream"
  git push -u origin "$HEAD"
else
  echo "  pushing $HEAD"
  git push origin "$HEAD"
fi

# Idempotency: reuse an existing open PR for this head branch.
EXISTING="$(gh pr list --head "$HEAD" --state open --json url --jq '.[0].url // ""')"
if [ -n "$EXISTING" ]; then
  echo "  PR already open: $EXISTING"
  exit 0
fi

gh pr create \
  --base "$BASE" \
  --head "$HEAD" \
  --title "$TITLE" \
  --body-file "$BODY_FILE" \
  $DRAFT
