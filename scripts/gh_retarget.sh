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
#   GraphQL: Projects (classic) is being deprecated ... (repository.pullRequest.projectCards)
#
# Nothing about that concerns the base branch, and the retarget does not happen.
# Both machines hit it independently on 2026-09-15 — gps3 on #213, the T420 on
# #221 — so the wrapper was broken for every stacked PR, not one case.
#
# WHY THE REPO IS PINNED AND NOT DISCOVERED
#
# The first version used `gh repo view --json nameWithOwner`, which resolves
# against the CURRENT DIRECTORY's remote. Measured, not reasoned about:
#
#   cwd = a checkout of savd-ai/ad-gen-simple  ->  savd-ai/ad-gen-simple
#   cwd = movefaults_clean                     ->  alfieprojectsdev/movefaults
#
# So invoking this by absolute path from another repository's directory would
# PATCH THAT REPOSITORY's PR of the same number — a write, returning 200,
# against the wrong project. gps3 alone has three other checkouts that could be
# the cwd, and one of the reachable repos is a private client one.
#
# That is CLAUDE.md's 2026-07-13 incident — acting on the wrong tree because
# the tool resolved context from the environment — except automated, and
# writing rather than reading.
#
# WHEN YOU NEED THIS
#
# Merging a base does NOT auto-retarget a stacked child. GitHub retargets only
# when the merged head branch is DELETED, and `merge_pr.sh` without
# `--delete-branch` does not delete it. The child then points at a merged
# branch while still reporting MERGEABLE and CLEAN — it looks fine and is not.
# CLAUDE.md rule 5, verify after every merge, is what catches it.
set -euo pipefail

pr="${1:?pr number}"
base="${2:?new base}"
# Override deliberately and visibly, or do not override.
repo="${GH_RETARGET_REPO:-alfieprojectsdev/movefaults}"

# No stream is discarded anywhere in this script. An earlier version sent the
# PATCH's stdout to a /tmp file it never read — discarding output with extra
# steps, eleven lines below a comment claiming nothing was discarded, inside
# the script written to fix that shape. It also leaked the file on failure,
# since `set -e` exits before the cleanup, and a guessable /tmp path opened
# with `>` follows symlinks.
patched=$(gh api -X PATCH "repos/${repo}/pulls/${pr}" -f base="${base}" -q '.base.ref')

# Two independent reads. A PATCH returning 200 having changed nothing is
# indistinguishable from one that worked if you only check the status, and a
# disagreement between the write's own answer and a fresh read is worth
# shouting about rather than smoothing over.
observed=$(gh api "repos/${repo}/pulls/${pr}" -q '.base.ref')

if [ "$patched" != "$observed" ]; then
    echo "FATAL: ${repo}#${pr} — PATCH reported '${patched}', read-back says '${observed}'" >&2
    exit 1
fi
if [ "$observed" != "$base" ]; then
    echo "FATAL: ${repo}#${pr} base is '${observed}', expected '${base}'" >&2
    exit 1
fi
# Name the repository. The old success line named neither, so output from a
# correct run and from one against the wrong project read identically.
echo "${repo}#${pr} base is now ${observed}"
