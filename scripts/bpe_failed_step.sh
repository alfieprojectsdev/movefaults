#!/usr/bin/env bash
# bpe_failed_step.sh — name the BPE step that failed in this attempt.
#
# Usage: scripts/bpe_failed_step.sh BPE_DIR YYSESS SINCE_EPOCH
#   BPE_DIR      the campaign's BPE/ directory ($P/<CAMPAIGN>/BPE)
#   YYSESS       two-digit year + session, e.g. 251220 for 2025 DOY 122
#   SINCE_EPOCH  when this attempt started (date +%s); older PRTs are ignored
#
# Prints one line, e.g.
#   PID 513 HELMCHK — *** PGM HELMR1: NO REDUNDANCY. ... (RS251220_513_000.PRT)
# and exits 0, or prints nothing and exits 1 when no step of this attempt failed.
#
# Why the PRT and not the BPE summary (<PCF>.OUT): the summary's last
# `NNN_NNN <word>` match is a row of its job table, so the old lookup reported
# every failure "at 0". The failed step's own PRT names the script and holds
# the error, and it is still there after the next day's BPE has rewritten the
# summary.
#
# Two things the PRTs do that this has to allow for:
#   * they are APPENDED, not rewritten (RUNBPE.pm's writePrtFileHeader opens
#     with `>>`), so only the block after the last "PROTOCOL FILE FOR BPE
#     SCRIPT" header is this attempt;
#   * steps that did not run this attempt keep their old files, so anything
#     not modified since SINCE_EPOCH is someone else's history.
set -uo pipefail

bpe_dir="${1:?BPE_DIR}"
tag="${2:?YYSESS}"
since="${3:?SINCE_EPOCH}"

# " 25-AUG-2026  07:45:54  00:00:01  00:00:00  ERR HELMR1    ERROR IN MAIN PROGRAM"
err_re='^[[:space:]]*[0-9]{2}-[A-Z]{3}-[0-9]{4}([[:space:]]+[0-9]{2}:[0-9]{2}:[0-9]{2})+[[:space:]]+ERR[[:space:]]'

last_attempt() {
    awk '/^[[:space:]]*PROTOCOL FILE FOR BPE SCRIPT[[:space:]]*$/ { buf = "" }
         { buf = buf $0 "\n" }
         END { printf "%s", buf }' "$1"
}

best="" best_t=0 best_text=""
shopt -s nullglob
# Glob order is name order, so among PRTs with the same mtime the highest PID wins.
for f in "$bpe_dir"/*"$tag"_[0-9][0-9][0-9]_[0-9][0-9][0-9].PRT; do
    t=$(stat -c %Y "$f" 2>/dev/null) || continue
    [ "$t" -ge "$since" ] || continue
    text=$(last_attempt "$f")
    grep -qE "$err_re" <<<"$text" || continue
    if [ "$t" -ge "$best_t" ]; then
        best=$f best_t=$t best_text=$text
    fi
done

[ -n "$best" ] || exit 1

name=$(basename "$best" .PRT)
pid=${name%_*}; pid=${pid##*_}
script=$(sed -nE 's/^[[:space:]]*Script name[[:space:]]*:[[:space:]]*([^[:space:]]+).*/\1/p' <<<"$best_text" | head -1)
# The cause is the last *** (error) block; ### is a warning, used only when no
# *** exists, so a warning printed after the error cannot stand in for it. A
# block's header names the routine and its first indented line often says what
# went wrong (CCRNXO: "No input files"), so both are shown.
message_block() {
    awk -v mark="$1" '
        function trim(s) { gsub(/^[[:space:]]+|[[:space:]]+$/, "", s); return s }
        $0 ~ "^[[:space:]]?" mark { hdr = trim($0); detail = ""; want = 1; next }
        want && /^[[:space:]][[:space:]]+[^[:space:]]/ { detail = trim($0); want = 0; next }
        { want = 0 }
        END { if (hdr != "") print (detail != "" ? hdr ": " detail : hdr) }'
}
msg=$(message_block '[*][*][*]' <<<"$best_text")
[ -n "$msg" ] || msg=$(message_block '###' <<<"$best_text")

printf 'PID %s %s' "$pid" "${script:-?}"
[ -n "$msg" ] && printf ' — %s' "$msg"
printf ' (%s)\n' "$(basename "$best")"
