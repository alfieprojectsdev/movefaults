#!/usr/bin/env bash
# merge_pr.sh — merge a GitHub PR (gated-write bypass; see open_pr.sh).
# Usage: scripts/merge_pr.sh <pr-number> [--squash|--merge] [--delete-branch]
#                            [--allow-red "<reason>"] [--no-local-ci "<reason>"] [--check]
#   --check  run the gate and report, but do not merge (exit 0 = would merge)
#
# LOCAL CI GATE (added with scripts/local_ci.py). Before merging, the PR's head
# commit must carry a `local-ci/gps3` status of `success`. Refused otherwise:
#   no status  -> gps3 never tested this commit: it may be down, asleep, or its
#                 cron stopped. Check with `scripts/local_ci.py status` on gps3.
#                 A check that silently never reports is the same failure as a
#                 workflow that never starts (SETTLED.md §6), so absence blocks.
#   pending    -> a run is in progress, or died mid-run.
#   failure / error -> the suite failed, or the harness did.
# Overrides take a reason, which is printed, so the bypass is a decision on the
# record rather than a habit: --allow-red for failure/error, --no-local-ci for
# a missing or pending status.
set -euo pipefail
PR="${1:?pr number required}"; shift || true
METHOD="--merge"; DELETE=""; ALLOW_RED=""; NO_LOCAL_CI=""; CHECK=""
# Hardcoded on purpose: no environment variable or config file can point the
# gate elsewhere or switch it off. The only bypasses are the two flags above,
# passed by hand, each with a reason.
SLUG="alfieprojectsdev/movefaults"
while [ $# -gt 0 ]; do case "$1" in
  --squash) METHOD="--squash";;
  --merge)  METHOD="--merge";;
  --delete-branch) DELETE="--delete-branch";;
  --allow-red|--no-local-ci)
    case "${2:-}" in ""|--*) echo "$1 needs a reason, e.g. $1 \"#243 is known and tracked\"" >&2; exit 2;; esac
    if [ "$1" = --allow-red ]; then ALLOW_RED="$2"; else NO_LOCAL_CI="$2"; fi; shift;;
  --check) CHECK=1;;
  *) echo "unknown arg: $1" >&2; exit 2;;
esac; shift; done

sha=$(gh pr view "$PR" -R "$SLUG" --json headRefOid -q .headRefOid)
state=$(gh api "repos/$SLUG/commits/$sha/statuses" \
          --jq '[.[]|select(.context=="local-ci/gps3")][0].state // "none"')
desc=$(gh api "repos/$SLUG/commits/$sha/statuses" \
          --jq '[.[]|select(.context=="local-ci/gps3")][0].description // ""')
echo "local-ci/gps3 on #$PR @ ${sha:0:7}: $state${desc:+ -- $desc}"

case "$state" in
  success) ;;
  failure|error)
    if [ -n "$ALLOW_RED" ]; then echo "override accepted (red): $ALLOW_RED"
    else echo "refused: local CI is $state. Fix it, or pass --allow-red \"<reason>\"." >&2; exit 3; fi;;
  none|pending)
    if [ -n "$NO_LOCAL_CI" ]; then echo "override accepted (no local CI result): $NO_LOCAL_CI"
    else echo "refused: no finished local CI result for this commit. Is gps3 up? (scripts/local_ci.py status)" >&2
         echo "         Pass --no-local-ci \"<reason>\" to merge anyway." >&2; exit 3; fi;;
  *) echo "refused: unexpected status '$state'" >&2; exit 3;;
esac

if [ -n "$CHECK" ]; then echo "gate passed; --check given, not merging"; exit 0; fi
# Bind the merge to the commit the gate judged. Without --match-head-commit, a
# push landing between the status check above and this line would be merged
# unchecked, while the gate reported success for a commit it never looked at.
# Applies to the override paths too: an override means "merge THIS red commit",
# not "merge whatever arrives next". (Raised in review of #251.)
gh pr merge "$PR" --match-head-commit "$sha" $METHOD $DELETE
