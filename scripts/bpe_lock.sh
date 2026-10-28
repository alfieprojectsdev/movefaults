# bpe_lock.sh -- take the machine's BPE lock from a shell driver. Source it.
#
# WHY
# Each scripts/ driver has its own lock (~/.run_luzon_month.lock and so on),
# which stops a second copy of the SAME script and nothing else. The service's
# bernese-run-year takes a machine-wide flock (bernese_workflow/bpe_lock.py),
# but the scripts did not, so a service run and a shell run could start on one
# machine and fight over USER.CPU, the BPE server and the campaign. This takes
# the same lock, on the same file, so either side refuses while the other runs.
#
# HOW
#   source "$(dirname "$0")/bpe_lock.sh"
#   bpe_lock_acquire "LUZON 2025 DOY 001-031" || die "machine is busy"
#
# The lock is a flock on $BPE_LOCK, else ~/.local/state/bernese-workflow/bpe.lock,
# the path bpe_lock.py uses. The kernel drops it when the last process holding
# the file descriptor exits. The descriptor is inherited by the BPE the driver
# starts, so if the driver is killed while the BPE runs on, the machine still
# reads as busy until the BPE ends -- which is the truth. The file records who
# holds it, in the JSON bpe_lock.py writes and reads, so a refusal on either
# side says who to ask.
#
# Requires flock(1) (util-linux).

bpe_lock_path() {
    printf '%s' "${BPE_LOCK:-$HOME/.local/state/bernese-workflow/bpe.lock}"
}

# Minimal JSON string escaping: backslash, double quote, control characters.
_bpe_lock_json() {
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr -d '\000-\037'
}

# bpe_lock_acquire PURPOSE
# Returns 0 holding the lock (descriptor in $BPE_LOCK_FD), 1 if another run
# holds it (the holder's record goes to stderr), 2 if the lock cannot be taken.
bpe_lock_acquire() {
    local purpose="${1:-}" path
    path=$(bpe_lock_path)
    command -v flock >/dev/null || { echo "bpe_lock: flock(1) not found" >&2; return 2; }
    mkdir -p "$(dirname "$path")" || return 2
    # Append, not truncate: a contender must not erase the record it is about
    # to report. The record is rewritten only once the lock is ours.
    exec {BPE_LOCK_FD}>>"$path" || return 2
    if ! flock -n "$BPE_LOCK_FD"; then
        echo "another BPE run holds $path: $(cat "$path" 2>/dev/null || echo 'no record')" >&2
        exec {BPE_LOCK_FD}>&-
        unset BPE_LOCK_FD
        return 1
    fi
    printf '{"pid": %d, "user": "%s", "host": "%s", "argv": ["%s"], "purpose": "%s", "started": "%s"}\n' \
        "$$" "$(_bpe_lock_json "$(id -un)")" "$(_bpe_lock_json "$(hostname)")" \
        "$(_bpe_lock_json "$0")" "$(_bpe_lock_json "$purpose")" \
        "$(date +%Y-%m-%dT%H:%M:%S)" > "$path"
    return 0
}
