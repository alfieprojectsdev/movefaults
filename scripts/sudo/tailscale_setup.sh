#!/usr/bin/env bash
# tailscale_setup.sh — put finch on the tailnet gps3 already belongs to.
#
# WHY
# finch drops off the network and stays off. The last outage ran from
# 2026-09-04 01:20:56 to 2026-09-07 15:58, and nobody could tell whether the
# machine was wedged, powered down, or simply unreachable from where they were
# standing. Six of its last nine boots ended abruptly (see
# ~/finch_shutdown_diagnosis.md). Tailscale does not fix that -- it makes the
# next one visible from anywhere instead of requiring a drive to the office.
#
# The actual fix is the watchdog in the headless-hardening playbook (PR #170),
# which reboots a wedged machine on its own. This is the observability that
# tells you whether the watchdog worked. Do both; do that one first if forced
# to choose.
#
# THE ONE THING THAT IS NOT LIKE gps3
# gps3 is Ubuntu 24.04 noble. **finch is Linux Mint 22.3 "zena"**, and
# Tailscale does not publish a `zena` suite:
#
#     https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg  -> 200
#     https://pkgs.tailscale.com/stable/ubuntu/zena.noarmor.gpg   -> 404
#
# Mint derives from Ubuntu and records its base in
# /etc/upstream-release/lsb-release (DISTRIB_CODENAME=noble). A script reading
# $VERSION_CODENAME from /etc/os-release would ask for `zena` and 404. This
# reads the upstream codename, and then VERIFIES the URL answers before adding
# a repository -- an apt source pointing at a 404 breaks every later apt run,
# not just this one.
#
# Apt repo rather than `curl | sh` so updates stay under normal package
# management.
#
# Usage:  sudo bash scripts/sudo/tailscale_setup.sh
# Safe to re-run; every step checks for its own result first.

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: run with sudo -- this installs a package and starts a daemon." >&2
    exit 1
fi

# The human who will own the node. SUDO_USER is set when invoked via sudo;
# without it, `tailscale status` would need root forever after.
LOGIN_USER="${SUDO_USER:-}"
if [ -z "$LOGIN_USER" ] || [ "$LOGIN_USER" = "root" ]; then
    echo "ERROR: could not determine the invoking user (SUDO_USER unset)." >&2
    echo "       Run as:  sudo bash $0" >&2
    exit 1
fi

TS_HOSTNAME="finch"     # what it will be called on the tailnet. The machine's
                        # own hostname is 't420'; everyone refers to it as
                        # finch, and the tailnet name is what people will type.

say() { printf '\n=== %s\n' "$*"; }

# ---------------------------------------------------------------- codename
say "Determining the Ubuntu base"

CODENAME=""
if [ -r /etc/upstream-release/lsb-release ]; then
    CODENAME=$(sed -n 's/^DISTRIB_CODENAME=//p' /etc/upstream-release/lsb-release)
    echo "  /etc/upstream-release says: $CODENAME"
fi
if [ -z "$CODENAME" ]; then
    CODENAME=$(sed -n 's/^VERSION_CODENAME=//p' /etc/os-release)
    echo "  no upstream-release file; falling back to /etc/os-release: $CODENAME"
fi
[ -n "$CODENAME" ] || { echo "ERROR: no codename could be determined." >&2; exit 1; }

BASE="https://pkgs.tailscale.com/stable/ubuntu"
say "Checking Tailscale publishes for '$CODENAME' before touching apt"
if ! curl -fsS -o /dev/null "$BASE/$CODENAME.noarmor.gpg"; then
    echo "ERROR: $BASE/$CODENAME.noarmor.gpg does not exist." >&2
    echo "       Adding it anyway would leave a broken apt source that breaks" >&2
    echo "       every future 'apt update', not just this script. Stopping." >&2
    exit 1
fi
echo "  OK — $CODENAME is published"

# ---------------------------------------------------------------- repo
say "Installing the signing key and apt source"
install -d -m 0755 /usr/share/keyrings
if [ -s /usr/share/keyrings/tailscale-archive-keyring.gpg ]; then
    echo "  keyring already present"
else
    curl -fsSL "$BASE/$CODENAME.noarmor.gpg" \
        > /usr/share/keyrings/tailscale-archive-keyring.gpg
    chmod 0644 /usr/share/keyrings/tailscale-archive-keyring.gpg
    echo "  keyring installed"
fi

if [ -s /etc/apt/sources.list.d/tailscale.list ]; then
    echo "  apt source already present:"
    sed 's/^/    /' /etc/apt/sources.list.d/tailscale.list
else
    curl -fsSL "$BASE/$CODENAME.tailscale-keyring.list" \
        > /etc/apt/sources.list.d/tailscale.list
    echo "  apt source installed"
fi

# ---------------------------------------------------------------- install
say "Installing tailscale"
if command -v tailscale >/dev/null 2>&1; then
    echo "  already installed: $(tailscale version | head -1)"
else
    # Scoped to this source: a full 'apt update' on a machine nobody has
    # touched for days can pull in surprises, and this script must never be
    # the thing that prompts a reboot -- the shutdown evidence in
    # ~/finch_lastboot.log is only reachable while the boot index holds.
    apt-get update \
        -o Dir::Etc::sourcelist=/etc/apt/sources.list.d/tailscale.list \
        -o Dir::Etc::sourceparts=/dev/null \
        -o APT::Get::List-Cleanup=0
    DEBIAN_FRONTEND=noninteractive apt-get install -y tailscale
fi

systemctl enable --now tailscaled
echo "  tailscaled: $(systemctl is-active tailscaled)"

# ---------------------------------------------------------------- DNS
say "Deciding the DNS flag"

# MagicDNS is safe to accept ONLY where systemd-resolved owns resolv.conf as a
# stub -- that is the split-DNS configuration, and Tailscale does not rewrite
# the file. Anywhere else, accepting DNS can replace the resolver and cut the
# machine off from names it needs locally.
RESOLV_TARGET=$(readlink -f /etc/resolv.conf 2>/dev/null || echo "")
DNS_FLAG="--accept-dns=false"
if systemctl is-active --quiet systemd-resolved \
   && [ "$RESOLV_TARGET" = "/run/systemd/resolve/stub-resolv.conf" ]; then
    DNS_FLAG=""
    echo "  systemd-resolved active with the stub resolv.conf — MagicDNS is"
    echo "  split-DNS here and safe to leave at the default."
else
    echo "  NOT the systemd-resolved stub configuration"
    echo "    systemd-resolved: $(systemctl is-active systemd-resolved 2>/dev/null || echo inactive)"
    echo "    /etc/resolv.conf -> ${RESOLV_TARGET:-<unresolved>}"
    echo "  passing --accept-dns=false so the resolver is left alone."
fi

# ---------------------------------------------------------------- join
say "Joining the tailnet"
echo "  A browser URL will be printed. Open it and authenticate."
echo
# shellcheck disable=SC2086
tailscale up --ssh --hostname="$TS_HOSTNAME" --operator="$LOGIN_USER" $DNS_FLAG

# ---------------------------------------------------------------- report
say "Result"
tailscale status || true
echo
echo "  tailnet IPv4: $(tailscale ip -4 2>/dev/null || echo '<not yet up>')"

say "Connection type"
echo "  Running netcheck. Either result below is fine:"
echo
echo "    UDP: true   — this host can hole-punch. On the 2026-09-07 run finch"
echo "                  reported UDP: true and reached gps3 DIRECTLY at"
echo "                  192.168.48.98:41641 in 76 ms, no relay involved."
echo "    UDP: false  — outbound UDP is blocked and traffic relays through"
echo "                  DERP (Singapore, ~30 ms). gps3 reports this. It still"
echo "                  works; it is simply not peer-to-peer. Do not chase it."
echo
echo "  The two machines differ because finch is DUAL-HOMED: enp0s25 on"
echo "  192.168.40.x carries the default route, while wlp3s0 sits on"
echo "  192.168.48.x — the same LAN as gps3. That shared subnet is why the"
echo "  peering is direct, and it is a property of where finch is plugged in,"
echo "  not of Tailscale. Expect it to change if the machine is moved."
echo
tailscale netcheck 2>&1 | sed 's/^/    /' || true

cat <<'CLOSING'

=== DO THIS NOW, OR finch WILL LEAVE THE TAILNET IN ~90 DAYS ===

  Open   https://login.tailscale.com/admin/machines
  Find   finch
  Set    Disable key expiry

Node keys expire by default. Re-authenticating needs a browser, and finch is
precisely the machine nobody is sitting at -- so when the key expires it will
drop off silently, and the disappearance will look exactly like the crash this
was installed to observe. That confusion is the whole reason to do it now.

=== AFTERWARDS ===

  tailscale status            (works without sudo, via --operator)
  ssh finch                   from any tailnet machine, Tailscale SSH is on
  tailscale ping gps3

Remote access only helps while the machine is still answering. The watchdog in
the headless-hardening playbook (PR #170) is what gets a wedged finch back on
its own -- that one matters more than this one.
CLOSING
