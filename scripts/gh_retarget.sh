#!/usr/bin/env bash
# gh_retarget.sh — change a PR's base branch (gated-write bypass).
# Usage: scripts/gh_retarget.sh <pr-number> <new-base>
#
# WHY NOT `gh pr edit --base`
#
# It fails on this repository. `gh pr edit` reads
# `repository.pullRequest.projectCards` as part of its GraphQL query, and
# Projects (classic) is deprecated:
#
#   GraphQL: Projects (classic) is being deprecated in favor of the new
#   Projects experience ... (repository.pullRequest.projectCards)
#
# Nothing about that is related to the base branch, and the retarget does not
# happen. Both machines hit it independently on 2026-09-15 — gps3 on #213,
# the T420 on #221 — so this wrapper has been broken for every stacked PR
# rather than for one.
#
# The REST endpoint touches no Projects field and works.
#
# WHEN YOU NEED THIS
#
# Merging a base does NOT auto-retarget a stacked child. GitHub retargets only
# when the merged head branch is DELETED, and `merge_pr.sh` without
# `--delete-branch` does not delete it. A stacked PR then points at a merged
# branch while still reporting MERGEABLE and CLEAN — it looks fine and is not.
# Verifying the base after every merge, per CLAUDE.md rule 5, is how that gets
# caught.
set -euo pipefail

pr="${1:?pr number}"
base="${2:?new base}"
repo=$(gh repo view --json nameWithOwner -q .nameWithOwner)

# No 2>/dev/null anywhere here. The first attempt at diagnosing this was run
# with stderr discarded, which hid the GraphQL error and made a failure look
# like a no-op — the defect this script exists to work around, repeated in the
# attempt to understand it.
gh api -X PATCH "repos/${repo}/pulls/${pr}" -f base="${base}" -q '.base.ref' > /tmp/.retarget.$$

# Assert the end state from the API rather than trusting the exit code: a PATCH
# that returns 200 having changed nothing is indistinguishable from one that
# worked, if you only read the status.
got=$(gh api "repos/${repo}/pulls/${pr}" -q '.base.ref')
rm -f /tmp/.retarget.$$
if [ "$got" != "$base" ]; then
    echo "FATAL: #${pr} base is '${got}', expected '${base}'" >&2
    exit 1
fi
echo "#${pr} base is now ${got}"
