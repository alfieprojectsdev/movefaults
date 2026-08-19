#!/usr/bin/env bash
# Reissue a fresh password for EVERY field account, in one pass.
#
#   ./scripts/reset_all_field_passwords.sh --slips field_credentials.txt
#   ./scripts/reset_all_field_passwords.sh --dry-run
#
# Why this exists
# ---------------
# seed_field_accounts.py creates accounts and writes their passwords to a slips
# file, but it deliberately NEVER rewrites an existing account's password — the
# holder may have been given it already, or changed it, and a re-run of the seed
# must not silently revoke that. Its escape hatch, --reset, takes one person at
# a time and prints once.
#
# That leaves no way to reissue the whole roster, which is what you need when
# the slips are lost, mixed up, printed on the wrong day, or handed to the wrong
# people. Doing it by hand is 13 invocations and 13 chances to lose one.
#
# This is destructive by design
# -----------------------------
# Every existing password stops working the moment this runs. Anyone already
# carrying a slip is locked out until they get the new one. That is the point —
# but it means this is the wrong tool if you only need one person's password
# replaced. Use `seed_field_accounts.py --reset INITIALS` for that.
#
# Passwords never reach the terminal or your shell history: each is captured
# from the seeder's stdout and written straight into the slips file, which is
# created 0600 before a byte is written.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROSTER="$ROOT/data/network_inventory/staff.csv"
SLIPS=""
DRY_RUN=0
ASSUME_YES=0

while [ $# -gt 0 ]; do
  case "$1" in
    --slips)   SLIPS="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --yes|-y)  ASSUME_YES=1; shift ;;
    -h|--help) sed -n '2,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

[[ -f "$ROSTER" ]] || { echo "roster not found: $ROSTER" >&2; exit 1; }

# Initials are the usernames — column 2 of the roster, header skipped.
mapfile -t PEOPLE < <(tail -n +2 "$ROSTER" | awk -F, 'NF>1 {gsub(/^[ \t]+|[ \t]+$/,"",$2); if ($2 != "") print toupper($2)}')
(( ${#PEOPLE[@]} )) || { echo "no initials found in $ROSTER" >&2; exit 1; }

if (( DRY_RUN )); then
  echo "would reissue passwords for ${#PEOPLE[@]} account(s):"
  printf '  %s\n' "${PEOPLE[@]}"
  echo
  echo "no password was generated and nothing was changed."
  exit 0
fi

[[ -n "$SLIPS" ]] || {
  echo "refusing to run: --slips PATH is required (or --dry-run to preview)." >&2
  echo "Without it every generated password would be unrecoverable." >&2
  exit 1
}

# Confirm, because this invalidates every slip already handed out.
if (( ! ASSUME_YES )); then
  echo "About to reissue passwords for ${#PEOPLE[@]} account(s):"
  printf '  %s\n' "${PEOPLE[@]}"
  echo
  echo "Every existing password stops working immediately."
  read -r -p "Type RESET to continue: " reply
  [[ "$reply" == "RESET" ]] || { echo "aborted."; exit 1; }
fi

umask 077
: > "$SLIPS"
chmod 600 "$SLIPS"
{
  echo "# Field Ops credentials — PRINT, DISTRIBUTE, THEN DESTROY"
  echo "# reissued $(date -u +%Y-%m-%dT%H:%M:%SZ) for all ${#PEOPLE[@]} accounts"
  echo "# shred -u this file once the slips are handed out."
  echo
} >> "$SLIPS"

failed=()
for who in "${PEOPLE[@]}"; do
  # The seeder prints "<INITIALS> password is now: <secret>". Capture it rather
  # than letting it reach the terminal; never echo the value from here.
  if out=$(cd "$ROOT" && uv run python scripts/seed_field_accounts.py --reset "$who" 2>&1); then
    pw=$(printf '%s\n' "$out" | sed -n 's/^.* password is now: //p' | head -1)
    if [[ -n "$pw" ]]; then
      printf '%s\t%s\n' "$who" "$pw" >> "$SLIPS"
      echo "  $who  reissued"
    else
      failed+=("$who (no password in output)")
      echo "  $who  FAILED — could not parse the new password"
    fi
  else
    # Most likely "no account for X": the roster has someone the database does
    # not. Report and keep going, so one gap does not stop the other twelve.
    failed+=("$who ($(printf '%s' "$out" | tail -1))")
    echo "  $who  FAILED"
  fi
done

echo
echo "$(( ${#PEOPLE[@]} - ${#failed[@]} )) of ${#PEOPLE[@]} reissued -> $SLIPS (mode 600)"
if (( ${#failed[@]} )); then
  echo "failures:"
  printf '  %s\n' "${failed[@]}"
fi
echo "Print it, hand each person their line, then: shred -u $SLIPS"
(( ${#failed[@]} == 0 ))
