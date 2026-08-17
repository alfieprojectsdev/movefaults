#!/usr/bin/env bash
#
# Bring the Field Ops stack up locally after a reboot.
#
#   ./scripts/field_ops_dev.sh          # start everything (default)
#   ./scripts/field_ops_dev.sh status   # what is running, and on which address
#   ./scripts/field_ops_dev.sh down     # stop the API and Vite (leaves the DB)
#   ./scripts/field_ops_dev.sh logs     # tail both server logs
#
# Starts, in order: the docker daemon (only if stopped), the Postgres
# container, the FastAPI backend, and the Vite dev server bound to all
# interfaces so a phone on the same wifi can reach it.
#
# ── Why this prints the LAN address every time ──────────────────────────────
#
# The address changed four times in one working day — office wifi, wired,
# home network, and once because the wifi interface dropped on its own. Every
# time it changed, the phone appeared to be broken when in fact the URL was
# simply stale. The address is re-read on every run and printed last, so what
# is on screen is always current.
#
# ── sudo ────────────────────────────────────────────────────────────────────
#
# Only reached when the docker daemon is actually stopped; most runs skip it.
# Prompts interactively by default. For unattended runs, either set
# FIELD_OPS_SUDO_PASS in the environment, or drop a scoped sudoers rule:
#
#   sudo visudo -f /etc/sudoers.d/docker-start
#   <username> ALL=(root) NOPASSWD: /usr/bin/systemctl start docker

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

API_DIR="services/field-ops"
WEB_DIR="services/field-ops/frontend"
LOG_DIR="${TMPDIR:-/tmp}/field-ops-dev"
API_LOG="$LOG_DIR/api.log"
WEB_LOG="$LOG_DIR/vite.log"
API_PORT=8001
WEB_PORT=5173
DB_PORT=5433

# Same default as docker-compose.yml, so an override in the environment reaches
# both the container and the readiness probe below rather than only the former.
DB_PASS="${POGF_DB_PASSWORD:-pogf_password}"

mkdir -p "$LOG_DIR"

bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
info() { printf '  %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

port_busy() { ss -ltn 2>/dev/null | grep -q ":$1 "; }

# ── docker daemon ───────────────────────────────────────────────────────────

start_docker() {
  if docker info >/dev/null 2>&1; then
    ok "docker daemon already running"
    return 0
  fi

  info "docker daemon is stopped — starting it needs root"
  if [[ -n "${FIELD_OPS_SUDO_PASS:-}" ]]; then
    # Here-string rather than a pipe from echo, so the password is never an
    # argument to a separate process and cannot show up in `ps`.
    sudo -S -p '' systemctl start docker <<<"$FIELD_OPS_SUDO_PASS" 2>/dev/null ||
      die "Could not start docker. Is FIELD_OPS_SUDO_PASS correct?"
  else
    sudo systemctl start docker || die "Could not start docker."
  fi

  # The socket appears a moment after systemctl returns.
  for _ in $(seq 1 20); do
    docker info >/dev/null 2>&1 && { ok "docker daemon started"; return 0; }
    sleep 1
  done
  die "docker started but the socket never became usable."
}

# ── database ────────────────────────────────────────────────────────────────

start_db() {
  docker compose up -d db >/dev/null 2>&1 || die "docker compose up -d db failed."

  # Readiness is not the same as "container running": the port is published
  # before Postgres accepts connections, and seeding against a not-yet-ready
  # database fails in a way that reads like a credentials problem.
  #
  # psql is not guaranteed to be installed on the host, so fall back to
  # pg_isready inside the container. That proves the server answers but cannot
  # count rows, which is why the station count is reported only on the first
  # path — a probe that lies about what it checked is worse than a quiet one.
  if ! command -v psql >/dev/null 2>&1; then
    for i in $(seq 1 45); do
      if docker compose exec -T db pg_isready -U pogf_user -d pogf_db >/dev/null 2>&1; then
        ok "database ready after ${i}s (pg_isready; install postgresql-client for the row count)"
        return 0
      fi
      sleep 1
    done
    die "Database did not become ready within 45s. Try: docker compose logs db"
  fi

  for i in $(seq 1 45); do
    if PGPASSWORD="$DB_PASS" PGCONNECT_TIMEOUT=2 \
       psql -h 127.0.0.1 -p "$DB_PORT" -U pogf_user -d pogf_db -tAc 'select 1' >/dev/null 2>&1; then
      local n
      n=$(PGPASSWORD="$DB_PASS" psql -h 127.0.0.1 -p "$DB_PORT" -U pogf_user -d pogf_db \
            -tAc 'select count(*) from public.stations' 2>/dev/null || echo '?')
      ok "database ready after ${i}s — ${n} stations"
      return 0
    fi
    sleep 1
  done
  die "Database did not accept connections within 45s. Try: docker compose logs db"
}

# ── servers ─────────────────────────────────────────────────────────────────

start_api() {
  if port_busy "$API_PORT"; then
    ok "API already listening on $API_PORT"
    return 0
  fi
  ( cd "$API_DIR" && nohup uv run field-ops-api >"$API_LOG" 2>&1 & )
  for i in $(seq 1 30); do
    curl -sf -o /dev/null --max-time 2 "http://127.0.0.1:$API_PORT/health" &&
      { ok "API up on $API_PORT after ${i}s"; return 0; }
    sleep 1
  done
  warn "API did not answer /health in 30s — see $API_LOG"
}

start_web() {
  if port_busy "$WEB_PORT"; then
    ok "Vite already listening on $WEB_PORT"
    return 0
  fi
  # --host binds every interface. Without it Vite listens on 127.0.0.1 only and
  # the phone cannot reach it, which looks exactly like the app being broken.
  ( cd "$WEB_DIR" && nohup npm run dev -- --host 0.0.0.0 >"$WEB_LOG" 2>&1 & )
  for i in $(seq 1 30); do
    curl -sf -o /dev/null --max-time 2 "http://127.0.0.1:$WEB_PORT/" &&
      { ok "Vite up on $WEB_PORT after ${i}s"; return 0; }
    sleep 1
  done
  warn "Vite did not answer in 30s — see $WEB_LOG"
}

# ── reporting ───────────────────────────────────────────────────────────────

lan_addresses() {
  ip -4 -br addr 2>/dev/null |
    grep -vE '^(lo|docker|veth|br-)' |
    awk '$2 == "UP" { split($3, a, "/"); print $1, a[1] }'
}

show_urls() {
  bold "Open"
  info "desktop   http://127.0.0.1:$WEB_PORT"
  local iface addr found=0
  while read -r iface addr; do
    [[ -z "$addr" ]] && continue
    info "phone     http://$addr:$WEB_PORT   ($iface)"
    found=1
  done < <(lan_addresses)
  (( found )) || warn "no LAN address — a phone will not be able to reach this"

  # Usernames are the initials in data/network_inventory/staff.csv; passwords
  # are surnames, which live only in the gitignored file that
  # scripts/seed_field_accounts.py reads. This repository is public, so no
  # credential is printed here — not even as an example.
  bold "Sign in"
  info "username = initials (data/network_inventory/staff.csv)"
  info "password = surname  (scripts/seed_field_accounts.py --reset INITIALS)"
  printf '\n  logs: %s\n        %s\n\n' "$API_LOG" "$WEB_LOG"
}

report() { # report <label> <up?>
  if "${@:2}" >/dev/null 2>&1; then ok "$1"; else warn "$1 — not running"; fi
}

cmd_status() {
  bold "Status"
  report "docker daemon"      docker info
  report "database  $DB_PORT" port_busy "$DB_PORT"
  report "API       $API_PORT" port_busy "$API_PORT"
  report "Vite      $WEB_PORT" port_busy "$WEB_PORT"
  show_urls
}

cmd_down() {
  bold "Stopping servers"
  # The database is deliberately left running: it is a container that restarts
  # with the machine anyway, and stopping it buys nothing while costing the
  # wait for it to come back.
  if pkill -f 'field-ops-api' 2>/dev/null; then ok "API stopped"; else info "API was not running"; fi
  if pkill -f 'vite' 2>/dev/null; then ok "Vite stopped"; else info "Vite was not running"; fi
  info "database left running (docker compose stop db to stop it too)"
}

cmd_up() {
  bold "Docker"
  start_docker
  bold "Database"
  start_db
  bold "Servers"
  start_api
  start_web
  show_urls
}

case "${1:-up}" in
  up)     cmd_up ;;
  status) cmd_status ;;
  down)   cmd_down ;;
  logs)   tail -f "$API_LOG" "$WEB_LOG" ;;
  *)      die "Usage: $(basename "$0") [up|status|down|logs]" ;;
esac
