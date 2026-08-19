#!/usr/bin/env bash
#
# Preflight gates. Sourced by deploy.sh; runs before anything touches a
# credential or a remote service.
#
# Every check here FAILS CLOSED: an unknown state is a stop, not a warning.
# The reason is the shape of this system — a half-provisioned deployment does
# not look broken. The API starts, the PWA loads, the login screen appears, and
# the failure only surfaces when an observer at a monument taps Submit. By then
# the diagnosis costs a site visit.
#
# Nothing in this file prints a secret. Checks report on variable NAMES and on
# derived facts (host, length, whether a default is still in place), never on
# values, because this output ends up in terminal scrollback and CI logs.

set -euo pipefail

FAILED=0

fail() { printf '  \033[31m✗\033[0m %s\n' "$*"; FAILED=$((FAILED + 1)); }
pass() { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }

# ── Tooling ────────────────────────────────────────────────────────────────

check_tools() {
  echo "Tooling"
  local missing=0
  for tool in uv psql; do
    if command -v "$tool" >/dev/null 2>&1; then
      pass "$tool"
    else
      fail "$tool is not installed — required for migrations and verification"
      missing=1
    fi
  done
  # Optional: only needed for the phases that use them, checked at point of use.
  for tool in vercel flyctl npx; do
    if command -v "$tool" >/dev/null 2>&1; then
      pass "$tool (optional)"
    else
      warn "$tool not installed — the phase that needs it will say so"
    fi
  done
  return $missing
}

# ── URL parsing ────────────────────────────────────────────────────────────

# Extract the hostname from a connection string without ever echoing the rest.
#
# This replaces a single sed substitution:
#
#     sed -E 's#^[^:]+://[^@]*@([^:/?]+).*#\1#'
#
# sed prints the line UNCHANGED when the pattern does not match, and that
# pattern requires an "@". A URL without one — the normal shape when the
# password comes from ~/.pgpass or PGPASSWORD rather than the string itself —
# fell straight through, so $host became the entire DATABASE_URL. Two
# consequences, both bad, and both observed:
#
#   1. pass() then printed it: "remote host: postgresql://user:pass@...".
#      This file promises at the top that it never prints a secret. It did.
#
#   2. Worse, the local-host case below matches exact names. A whole URL
#      matches none of them, so `postgresql://localhost:5433/pogf_db` was
#      reported as "✓ remote host" and preflight passed — then `deploy.sh db`
#      migrates the local container while the operator believes it is hitting
#      Neon. That is precisely the wrong-database failure the comment above
#      check_database_target describes having already happened once, and the
#      check written to prevent it was failing OPEN.
#
# Pure shell parameter expansion: no subprocess, no regex, no way to fall
# through to "the input unchanged". An unparseable URL returns non-zero and the
# caller fails closed.
url_host() {
  local rest="$1"

  case "$rest" in
    *://*) rest="${rest#*://}" ;;
    *) return 1 ;;                # no scheme — refuse rather than guess
  esac

  rest="${rest%%\?*}"             # drop ?query
  rest="${rest%%/*}"              # drop /path
  rest="${rest##*@}"              # drop userinfo; LAST @ wins, so a password
                                  # containing @ does not truncate the host

  case "$rest" in
    \[*\]*)                       # IPv6 literal: [::1]:5432
      rest="${rest%%\]*}"
      rest="${rest#\[}"
      ;;
    *) rest="${rest%%:*}" ;;      # drop :port
  esac

  [[ -n "$rest" ]] || return 1
  printf '%s' "$rest"
}

# ── Database target ────────────────────────────────────────────────────────

# The single most expensive mistake this script can make is migrating and
# seeding the wrong database. It happened during development: both alembic
# trees read only POGF_DB_*, so a documented `export DATABASE_URL=...` ran
# against a local container while the hosted database stayed empty — and
# `alembic upgrade head` printed success either way.
check_database_target() {
  echo "Database target"

  if [[ -z "${DATABASE_URL:-}" ]]; then
    fail "DATABASE_URL is not set"
    echo "      Export the POOLED Neon connection string (host contains '-pooler')."
    return 1
  fi

  local host
  if ! host=$(url_host "$DATABASE_URL"); then
    fail "DATABASE_URL is not a parseable URL"
    echo "      Expected postgresql://[user[:password]@]host[:port]/dbname"
    echo "      No part of the value is printed here — check it in your"
    echo "      password manager, not by echoing it."
    return 1
  fi

  case "$host" in
    localhost|127.0.0.1|::1|db|postgres|host.docker.internal)
      if [[ "${ALLOW_LOCAL_TARGET:-}" == "1" ]]; then
        warn "target is LOCAL ($host) — permitted by ALLOW_LOCAL_TARGET=1"
      else
        fail "DATABASE_URL points at $host, which is local"
        echo "      This script provisions a deployment. Set ALLOW_LOCAL_TARGET=1"
        echo "      only if you are deliberately rehearsing against a container."
        return 1
      fi
      ;;
    *)
      pass "remote host: $host"
      ;;
  esac

  # Neon's own advice, and it bites on a container that restarts: the direct
  # endpoint runs out of connections where the pooled one does not.
  if [[ "$host" == *neon.tech* && "$host" != *-pooler* ]]; then
    warn "this looks like Neon's DIRECT endpoint — prefer the pooled one"
    echo "      Neon dashboard → your project → Connection Details →"
    echo "      Connection string → tick 'Pooled connection'"
  fi

  # Capture psql's error instead of discarding it. This check used to run with
  # `>/dev/null 2>&1`, so every failure — an idle Neon endpoint still waking up,
  # a libpq too old for `channel_binding`, DNS, a genuinely wrong password —
  # produced the same four words and the same advice: go re-read your password
  # manager. That advice is right for exactly one of those causes and wastes an
  # operator's time on the other three.
  #
  # The error is REDACTED before printing. libpq does not normally echo the
  # connection string, but "does not normally" is not the promise this file
  # makes at the top, and this output lands in terminal scrollback and CI logs.
  local err rc=0
  err=$(psql "$DATABASE_URL" -tAc 'select 1' 2>&1 >/dev/null) || rc=$?

  if (( rc != 0 )); then
    fail "cannot connect to the database"
    printf '%s\n' "$err" \
      | sed -E 's#://[^@[:space:]]*@#://***:***@#g' \
      | sed 's/^/      /'
    echo
    echo "      Host parsed from DATABASE_URL: $host"
    case "$err" in
      *"invalid connection option"*|*"channel_binding"*)
        echo "      Your libpq is older than the options in the string. Neon"
        echo "      appends channel_binding=require, which needs libpq >= 13."
        echo "      It is a client preference, not a server requirement — retry"
        echo "      without it:"
        echo "        psql \"\${DATABASE_URL%%&channel_binding=*}\" -tAc 'select 1'"
        ;;
      *"could not translate host name"*|*"Name or service not known"*)
        echo "      DNS did not resolve that host. Check for a truncated or"
        echo "      line-wrapped connection string."
        ;;
      *"password authentication failed"*|*"authentication"*)
        echo "      The host is reachable and rejected the credentials. If you"
        echo "      just rotated the password, re-export DATABASE_URL — the old"
        echo "      value is still in this shell."
        ;;
      *"timeout"*|*"timed out"*|*"Connection refused"*)
        echo "      Reachability, not credentials. A Neon endpoint suspended for"
        echo "      idleness takes a few seconds on the first connect — retry"
        echo "      once before changing anything."
        ;;
    esac
    return 1
  fi
  pass "connection succeeds"
}

# ── Application secrets ────────────────────────────────────────────────────

# Names and derived facts only. `FIELD_OPS_JWT_SECRET` in particular must never
# be echoed: the whole point of this check is that a weak one is catastrophic.
check_backend_env() {
  echo "Backend configuration"

  local required=(
    FIELD_OPS_JWT_SECRET
    FIELD_OPS_STORAGE_BACKEND
    R2_ACCOUNT_ID
    R2_ACCESS_KEY_ID
    R2_SECRET_ACCESS_KEY
    R2_BUCKET
  )
  local name
  for name in "${required[@]}"; do
    if [[ -z "${!name:-}" ]]; then
      fail "$name is not set"
    else
      pass "$name is set"
    fi
  done

  if [[ -n "${FIELD_OPS_JWT_SECRET:-}" ]]; then
    if [[ "$FIELD_OPS_JWT_SECRET" == "change-me-in-production" ]]; then
      fail "FIELD_OPS_JWT_SECRET is still the shipped default"
      echo "      That default is published in this PUBLIC repository. Anyone"
      echo "      who reads it can mint a valid token for your URL."
    elif (( ${#FIELD_OPS_JWT_SECRET} < 32 )); then
      fail "FIELD_OPS_JWT_SECRET is under 32 characters"
    else
      pass "FIELD_OPS_JWT_SECRET is not the default and is long enough"
    fi
  fi

  if [[ "${FIELD_OPS_STORAGE_BACKEND:-}" != "r2" ]]; then
    fail "FIELD_OPS_STORAGE_BACKEND must be 'r2' for a deployment"
    echo "      A container filesystem is ephemeral: photos written to disk are"
    echo "      gone on the next restart, while the database still points at them."
  fi

  if [[ -n "${FIELD_OPS_DEV:-}" ]]; then
    fail "FIELD_OPS_DEV is set — this disables every check above at runtime"
  fi
}

# ── Repository state ───────────────────────────────────────────────────────

check_repo_state() {
  echo "Repository"

  if [[ -f services/field-ops/frontend/vercel.json ]] &&
     grep -q 'REPLACE-WITH-BACKEND-HOST' services/field-ops/frontend/vercel.json; then
    warn "vercel.json still holds the placeholder backend host"
    echo "      Fine until you deploy the frontend; the build refuses it on Vercel."
  else
    pass "vercel.json backend host is set"
  fi

  local dirty
  dirty=$(git status --porcelain 2>/dev/null | grep -vc '^??' || true)
  if [[ "$dirty" != "0" ]]; then
    warn "$dirty tracked file(s) modified — deploying something not committed"
  else
    pass "no uncommitted changes to tracked files"
  fi
}

run_preflight() {
  local scope="${1:-all}"
  FAILED=0

  # Each check reports through fail(), which increments FAILED; a non-zero
  # return just means "stopped early". `|| true` keeps `set -e` from aborting
  # before the remaining checks have had their say, so one run lists every
  # problem rather than making the operator rediscover them one at a time.
  check_tools || true
  check_database_target || true
  if [[ "$scope" == "all" || "$scope" == "backend" ]]; then
    check_backend_env || true
  fi
  check_repo_state || true

  echo
  if (( FAILED > 0 )); then
    printf '\033[31m%d preflight check(s) failed. Nothing has been changed.\033[0m\n' "$FAILED"
    return 1
  fi
  printf '\033[32mPreflight clean.\033[0m\n'
}
