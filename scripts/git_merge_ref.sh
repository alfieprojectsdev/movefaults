#!/usr/bin/env bash
# git_merge_ref.sh — merge a given ref into the current branch (gated-write bypass).
set -uo pipefail
git merge "${1:?ref}" --no-edit
