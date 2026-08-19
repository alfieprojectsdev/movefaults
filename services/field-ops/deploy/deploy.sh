#!/usr/bin/env bash
#
# Field Ops deployment runner.
#
#   ./services/field-ops/deploy/deploy.sh preflight
#   ./services/field-ops/deploy/deploy.sh db        [--dry-run]
#   ./services/field-ops/deploy/deploy.sh seed      [--dry-run]
#   ./services/field-ops/deploy/deploy.sh accounts  --slips FILE [--dry-run]
#   ./services/field-ops/deploy/deploy.sh verify
#
# ── What this does and does not do ─────────────────────────────────────────
#
# This is not "one command deploys everything", and presenting it that way
# would be a lie with consequences. Creating accounts, accepting terms, issuing
# API tokens and pasting connection strings are steps a person must perform in
# each platform's own interface — this script never does them, never asks for a
# password, and never handles a credential it was not given through the
# environment.
#
# What it does own is every step that is mechanical and every step that has a
# verifiable result: migrations in the one order that works, seeding, account
# creation from a roster, and an end-to-end check that the deployment actually
# answers. Those are the steps where a human doing it by hand at 11pm before a
# field trip gets it subtly wrong.
#
# The manual steps, with the exact interface path to click, are in
# services/field-ops/DEPLOY.md. Run `preflight` first; it will tell you which
# ones are outstanding.
#
# ── Honesty about what has been exercised ──────────────────────────────────
#
# The `db`, `seed`, `accounts` and `verify` phases have been run end to end
# against a local Postgres. The `frontend` phase and every remote-platform
# interaction have NOT been executed against real infrastructure — no Neon
# project, no Fly app, no Vercel deployment has been provisioned from this
# script. Treat those paths as inert rather than proven, and run them with
# --dry-run first.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

# Sourced by path relative to this file, not to the caller's CWD, so the script
# works from anywhere.
# shellcheck disable=SC1091  # path is dynamic; resolved at runtime, not statically
source "$(dirname "${BASH_SOURCE[0]}")/preflight.sh"

DRY_RUN=0
SURNAMES=""
SLIPS=""

say()  { printf '\n\033[1m── %s\033[0m\n' "$*"; }
step() { printf '  %s\n' "$*"; }
stop() { printf '\n\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

# A phase that would change something remote announces it, so a --dry-run
# transcript reads as a plan rather than as silence.
would() {
  if (( DRY_RUN )); then
    printf '  \033[33m[dry-run]\033[0m %s\n' "$*"
    return 0
  fi
  return 1
}

# ── Phases ─────────────────────────────────────────────────────────────────

phase_db() {
  run_preflight db || stop "Fix the above before migrating."

  say "Migrations"
  # Order is load-bearing and not obvious: root revision 008 extends
  # field_ops.logsheets and field_ops.staff, which fo001 creates. Running the
  # root tree first against an empty database fails with
  # 'schema "field_ops" does not exist'. This was documented backwards until
  # 2026-08-11 and had never been run against a genuinely empty database.
  step "field_ops tree first (creates the schema root/008 depends on)"
  would "uv run alembic -c services/field-ops/alembic.ini upgrade head" ||
    uv run alembic -c services/field-ops/alembic.ini upgrade head

  step "root tree second"
  would "uv run alembic upgrade head" || uv run alembic upgrade head

  (( DRY_RUN )) && return 0

  say "Verifying schema"
  # Trusting the exit status is exactly the mistake that let a 'successful'
  # migration land on the wrong database. Check the objects exist.
  local tables
  tables=$(psql "$DATABASE_URL" -tAc \
    "select count(*) from information_schema.tables where table_schema='field_ops'")
  step "field_ops tables: $tables (expect 7 or more)"
  (( tables >= 7 )) || stop "Schema incomplete — do not continue."

  psql "$DATABASE_URL" -tAc \
    "select 1 from information_schema.columns
      where table_schema='field_ops' and table_name='logsheet_photos'
        and column_name='content_sha256'" | grep -q 1 ||
    stop "logsheet_photos.content_sha256 missing — fo003 did not run."
  step "photo idempotency column present"
}

phase_seed() {
  run_preflight db || stop "Fix the above before seeding."

  say "Seeding stations, equipment and observers"
  if (( DRY_RUN )); then
    uv run python scripts/seed_network_inventory.py --dry-run
  else
    uv run python scripts/seed_network_inventory.py
  fi
}

phase_accounts() {
  # Random passwords are the default, matching seed_field_accounts.py since
  # 2026-08-19. This wrapper used to REQUIRE --surnames and pass it straight
  # through, which meant the retired scheme could still be reached here after
  # the seeder itself had moved on — surname passwords on a public URL, by way
  # of a flag nobody thought to stop passing.
  if [[ -n "$SURNAMES" ]]; then
    [[ -f "$SURNAMES" ]] || stop "$SURNAMES not found."
  else
    [[ -n "$SLIPS" || $DRY_RUN -eq 1 ]] || stop \
      "accounts needs --slips FILE (where the generated passwords are written), \
or --surnames FILE for the legacy scheme on an instance that is genuinely \
unreachable from the internet."
  fi
  run_preflight db || stop "Fix the above before creating accounts."

  say "Observer accounts"
  # Both files are credential lists. Neither is printed or copied here, and the
  # seeder reports initials only.
  local args=()
  if [[ -n "$SURNAMES" ]]; then
    args+=(--surnames "$SURNAMES")
  elif [[ -n "$SLIPS" ]]; then
    args+=(--slips "$SLIPS")
  fi
  if (( DRY_RUN )); then
    uv run python scripts/seed_field_accounts.py "${args[@]}" --dry-run
  else
    uv run python scripts/seed_field_accounts.py "${args[@]}"
    if [[ -n "$SURNAMES" ]]; then
      step "Delete $SURNAMES once the accounts exist: shred -u $SURNAMES"
    else
      step "Print $SLIPS, hand out the slips, then: shred -u $SLIPS"
    fi
  fi
}

# phase_frontend was here. Retired 2026-08-19 when the frontend moved to
# Vercel's Git integration, which is the model the backend already used:
# render.yaml is read from main and redeploys on merge.
#
# It worked by `sed`-ing the placeholder in vercel.json and running
# `vercel deploy --prod` from the working tree. Two problems with keeping that
# alongside a Git-driven backend:
#
#   * only the machine that ran the sed could deploy, and nothing in git
#     described what was deployed
#   * once the placeholder was substituted and committed, the sed silently
#     no-opped and the `grep -q ... && stop` guard passed, so --backend-host was
#     ignored and the deploy went to whatever host happened to be in the file.
#     Pointing it at staging would have deployed production.
#
# Both disappear when Vercel builds from the repository. The frontend now
# deploys by merging to main; see DEPLOY.md section 4.

phase_verify() {
  local base="${FIELD_OPS_URL:-}"
  [[ -n "$base" ]] || stop "verify needs FIELD_OPS_URL (the deployed PWA URL)."

  say "End-to-end verification against $base"

  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$base/api/v1/stations" || echo 000)
  # 401 is the correct answer to an unauthenticated request and proves the API
  # is reachable through the rewrite. 200 would mean the endpoint is open.
  case "$code" in
    401) step "API reachable through the frontend, and requires auth" ;;
    200) stop "GET /api/v1/stations returned 200 unauthenticated — endpoint is open." ;;
    000) stop "No response. Check the /api rewrite in vercel.json." ;;
    *)   stop "Unexpected $code from /api/v1/stations." ;;
  esac

  if [[ -n "${DATABASE_URL:-}" ]]; then
    local stations staff
    stations=$(psql "$DATABASE_URL" -tAc "select count(*) from public.stations")
    staff=$(psql "$DATABASE_URL" -tAc "select count(*) from field_ops.staff")
    step "stations seeded: $stations"
    step "observers seeded: $staff"
    (( stations > 10 )) || stop "Only $stations stations — the seed did not run here."
  fi

  cat <<'MANUAL'

  Automated checks stop here. These cannot be scripted and are the ones that
  decide whether the fieldwork works — do them on a real phone:

    [ ] Sign in as a real observer
    [ ] Station list shows the sites being visited
    [ ] Add to Home Screen; it opens without browser chrome
    [ ] Airplane mode: file a full sheet with a photo
        expect "Saved offline — including the photo"
    [ ] Signal back on: the queue drains by itself
    [ ] logsheet_photos has a row with an r2:// path, and the object opens
    [ ] Force-quit between queueing and syncing, reopen — sheet still there

  The airplane-mode step is the one most likely to be skipped and the one whose
  failure is silent. See services/field-ops/FIELD_RUNBOOK.md.
MANUAL
}

# ── Entry ──────────────────────────────────────────────────────────────────

CMD="${1:-}"; shift || true
while (( $# )); do
  case "$1" in
    --dry-run)      DRY_RUN=1 ;;
    --surnames)     SURNAMES="${2:-}"; shift ;;
    --slips)        SLIPS="${2:-}"; shift ;;
    *) stop "Unknown option: $1" ;;
  esac
  shift
done

case "$CMD" in
  preflight) run_preflight all ;;
  db)        phase_db ;;
  seed)      phase_seed ;;
  accounts)  phase_accounts ;;
  verify)    phase_verify ;;
  *)
    sed -n '3,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    echo
    echo "Manual steps, with interface paths: services/field-ops/DEPLOY.md"
    exit 1
    ;;
esac
