#!/usr/bin/env bash
# mirror-update.sh — refresh the PHIVOLCS-held mirror of the movefaults repo
#
# WHY THIS EXISTS: the code of record lives on a personal GitHub account
# (alfieprojectsdev/movefaults) that nobody at PHIVOLCS can grant access to.
# The risk is not losing the GNSS data — it is losing the knowledge of how to
# process it. This mirror puts that knowledge on agency hardware.
#
# This script lives WITH the mirror on /srv/gnss-archive rather than only in
# the repo, deliberately: a recovery tool that only exists inside the thing it
# recovers is not a recovery tool. The version-controlled copy is at
# scripts/gnss_mirror_update.sh.
#
# NO --prune, ON PURPOSE. COORDINATION.md §6 suggests
# `git remote update --prune`, which is the right default for a convenience
# mirror and the WRONG one here. --prune deletes local refs that vanished
# upstream, so a deleted branch, a repo takedown, or an account closure would
# propagate the loss straight into the only agency-held copy — defeating the
# entire point. Without it, stale refs accumulate; that costs kilobytes.
#
# Paired settings on the mirror (set once, verified below):
#   core.logAllRefUpdates=true  bare repos default to OFF. With it on, an
#                               upstream force-push leaves the old tip in the
#                               reflog instead of silently vanishing.
#   gc.pruneExpire=never        keeps unreachable objects, so history removed
#                               upstream stays recoverable here.
#
# Together: this mirror is append-only in practice. Upstream cannot destroy
# history in it, only add to it.
#
# Usage:  /srv/gnss-archive/git/mirror-update.sh          (cron-safe, quiet)
#         /srv/gnss-archive/git/mirror-update.sh --verbose
set -uo pipefail

MIRROR="/srv/gnss-archive/git/movefaults.git"
LOG="/srv/gnss-archive/git/mirror-update.log"
VERBOSE=0
[ "${1:-}" = "--verbose" ] && VERBOSE=1

# Fail fast instead of hanging on a passphrase prompt: cron has no tty, and a
# blocked ssh would leave this script running until the next invocation.
export GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=20"
export GIT_TERMINAL_PROMPT=0

log() { printf '%s %s\n' "$(date -Is)" "$*" >> "$LOG"; [ "$VERBOSE" = 1 ] && printf '%s\n' "$*"; return 0; }

[ -d "$MIRROR" ] || { log "FATAL mirror missing at $MIRROR"; exit 1; }

# Refuse to run if the archive volume is not actually mounted. Otherwise a
# failed mount turns this into a script that writes a fresh empty mirror onto
# the root filesystem and reports success.
if ! mountpoint -q /srv/gnss-archive; then
    log "FATAL /srv/gnss-archive is not a mountpoint — refusing to run"
    exit 1
fi

# Record the tips BEFORE, so the log says what actually changed rather than
# just "ran ok". Capture-then-compare; do not pipe into a test (a `slow_cmd |
# grep -q` under pipefail returns 141 when the reader exits first — that bug
# cost this project a debugging session on 2026-07-30).
before=$(git --git-dir="$MIRROR" for-each-ref --format='%(refname) %(objectname)' refs/heads 2>/dev/null)

if ! out=$(git --git-dir="$MIRROR" remote update 2>&1); then
    log "FAIL fetch failed:"
    printf '%s\n' "$out" | sed 's/^/    /' >> "$LOG"
    exit 1
fi

after=$(git --git-dir="$MIRROR" for-each-ref --format='%(refname) %(objectname)' refs/heads 2>/dev/null)

nb=$(printf '%s\n' "$before" | grep -c . )
na=$(printf '%s\n' "$after"  | grep -c . )
if [ "$before" = "$after" ]; then
    log "ok   no change ($na branches)"
else
    changed=$(diff <(printf '%s\n' "$before") <(printf '%s\n' "$after") | grep -cE '^[<>]' || true)
    log "ok   updated — branches $nb -> $na, $changed ref lines changed"
fi

# Integrity check. For a git mirror, object hashing IS the fixity mechanism —
# fsck verifies every object against its own SHA, which is exactly the silent
# bit-rot detection COORDINATION.md §6 item 4 asks for. The repo is ~14 MB, so
# there is no reason to sample or schedule this separately.
if fsck_out=$(git --git-dir="$MIRROR" fsck --no-progress 2>&1); then
    [ -n "$fsck_out" ] && { log "warn fsck output:"; printf '%s\n' "$fsck_out" | sed 's/^/    /' >> "$LOG"; }
    log "ok   fsck clean"
else
    log "FAIL fsck reported corruption — investigate before trusting this copy:"
    printf '%s\n' "$fsck_out" | sed 's/^/    /' >> "$LOG"
    exit 1
fi

# Keep the log from growing without bound.
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 2000 ]; then
    tail -1000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
exit 0
