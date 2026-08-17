#!/usr/bin/env bash
#
# Field Ops deployment runner.
#
#   ./services/field-ops/deploy/deploy.sh preflight
#   ./services/field-ops/deploy/deploy.sh db        [--dry-run]
#   ./services/field-ops/deploy/deploy.sh seed      [--dry-run]
#   ./services/field-ops/deploy/deploy.sh accounts  --surnames FILE [--dry-run]
#   ./services/field-ops/deploy/deploy.sh frontend  --backend-host HOST
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
BACKEND_HOST=""

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
  [[ -n "$SURNAMES" ]] || stop "accounts needs --surnames FILE (INITIALS,surname)."
  [[ -f "$SURNAMES" ]] || stop "$SURNAMES not found."
  run_preflight db || stop "Fix the above before creating accounts."

  say "Observer accounts"
  # The surname file is a credential list. It is never printed, never copied,
  # and the seeder reports only initials.
  if (( DRY_RUN )); then
    uv run python scripts/seed_field_accounts.py --surnames "$SURNAMES" --dry-run
  else
    uv run python scripts/seed_field_accounts.py --surnames "$SURNAMES"
    step "Delete $SURNAMES once the accounts exist: shred -u $SURNAMES"
  fi
}

phase_frontend() {
  command -v vercel >/dev/null 2>&1 || stop \
    "vercel CLI not installed. npm i -g vercel, then 'vercel login'."
  [[ -n "$BACKEND_HOST" ]] || stop \
    "frontend needs --backend-host HOST (e.g. pogf-field-ops.fly.dev)."

  case "$BACKEND_HOST" in
    https://*|http://*) stop "--backend-host takes a bare hostname, no scheme." ;;
  esac

  say "Frontend"
  local cfg="services/field-ops/frontend/vercel.json"

  # The rewrite keeps the API same-origin, which removes a CORS preflight —
  # one fewer round trip on one bar of signal. The placeholder must be gone
  # before the build, and check-deploy-config.mjs fails the build if it is not.
  step "pointing the /api rewrite at $BACKEND_HOST"
  would "sed -i 's|REPLACE-WITH-BACKEND-HOST|$BACKEND_HOST|' $cfg" || {
    sed -i "s|REPLACE-WITH-BACKEND-HOST|${BACKEND_HOST}|" "$cfg"
    grep -q 'REPLACE-WITH-BACKEND-HOST' "$cfg" &&
      stop "placeholder still present in $cfg — edit it by hand."
  }

  step "deploying to Vercel (production)"
  would "vercel deploy --prod --cwd services/field-ops/frontend" ||
    vercel deploy --prod --cwd services/field-ops/frontend
}

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
    --backend-host) BACKEND_HOST="${2:-}"; shift ;;
    *) stop "Unknown option: $1" ;;
  esac
  shift
done

case "$CMD" in
  preflight) run_preflight all ;;
  db)        phase_db ;;
  seed)      phase_seed ;;
  accounts)  phase_accounts ;;
  frontend)  phase_frontend ;;
  verify)    phase_verify ;;
  *)
    sed -n '3,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    echo
    echo "Manual steps, with interface paths: services/field-ops/DEPLOY.md"
    exit 1
    ;;
esac
