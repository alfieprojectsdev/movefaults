#!/usr/bin/env bash
# finch_ssh_enable.sh — two independent ways in to a machine nobody can reach.
#
# WHY BOTH
# gps3 opened a TCP connection to finch on the tailnet and got no answer at
# all: Linux Mint ships no sshd. So the tailnet works finch -> gps3 and not
# back, which is the wrong direction for a machine that hangs.
#
#   openssh-server   works whenever there is a route -- LAN included -- and
#                    does not care whether Tailscale or its control plane is
#                    up. This is the path that survives a tailnet outage.
#   Tailscale SSH    no key distribution; access follows tailnet identity.
#
# Belt and braces, for a box that ends 7 of its last 10 boots abruptly and now
# lives somewhere nobody can walk to.
#
# Usage:  sudo bash scripts/sudo/finch_ssh_enable.sh
# Safe to re-run.

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: run with sudo." >&2
    exit 1
fi

say() { printf '\n=== %s\n' "$*"; }

# ---------------------------------------------------------------- openssh
say "openssh-server"
if dpkg -s openssh-server >/dev/null 2>&1; then
    echo "  already installed"
else
    # Scoped update. A broad one on this machine can pull a kernel and prompt
    # a reboot, and reboots here destroy journal evidence by shifting the boot
    # index.
    DEBIAN_FRONTEND=noninteractive apt-get install -y openssh-server
fi

# Debian and Mint socket-activate sshd. Under socket activation `ssh.service`
# reads INACTIVE while `ssh.socket` is ACTIVE and everything is fine -- that
# reading has already sent one session chasing a non-problem on gps3. Enable
# the socket if it exists, and fall back to the service if this build does not
# use socket activation.
if systemctl list-unit-files ssh.socket >/dev/null 2>&1 && \
   systemctl cat ssh.socket >/dev/null 2>&1; then
    systemctl enable --now ssh.socket
    echo "  ssh.socket enabled (socket activation)"
else
    systemctl enable --now ssh
    echo "  ssh.service enabled (no socket activation on this build)"
fi

say "Is anything actually listening on 22?"
# The real test. Not `systemctl is-active`, which reads `inactive` for a
# perfectly healthy socket-activated sshd.
if ss -lntp 2>/dev/null | grep -q ':22 '; then
    ss -lntp 2>/dev/null | grep ':22 ' | sed 's/^/  /'
else
    echo "  NOTHING LISTENING ON 22 — this is the failure, investigate before"
    echo "  trusting this path. Check: systemctl status ssh.socket ssh.service"
fi

echo
echo "  PermitRootLogin: $(sshd -T 2>/dev/null | grep -i '^permitrootlogin' || echo '(sshd -T unavailable)')"
echo "  Left at the distro default. The machine is behind NAT with no port"
echo "  forwarding, so it is not internet-reachable; no further hardening"
echo "  tonight, deliberately."

# ---------------------------------------------------------------- tailscale
say "Tailscale SSH"
if ! command -v tailscale >/dev/null 2>&1; then
    echo "  tailscale not installed — skipping."
else
    # `tailscale set --ssh`, NOT `tailscale up --ssh`.
    #
    # `up` re-specifies the ENTIRE configuration: any flag not repeated is
    # dropped. Running `tailscale up --ssh` here would silently discard
    # --hostname=finch and --operator=finch, renaming the node and taking
    # `tailscale status` back to needing root. `set` changes one setting.
    tailscale set --ssh
    echo "  --ssh set"
    if tailscale status --json 2>/dev/null | grep -qi '"RunSSH": *true'; then
        echo "  RunSSH: true"
    else
        echo "  RunSSH not reported true — check 'tailscale status --json'"
    fi
fi

cat <<'CLOSING'

=== STILL NEEDED FROM THE ADMIN CONSOLE ===

Tailscale SSH does nothing until the tailnet policy has an `ssh` block. If it
is absent the connection is REFUSED -- it does NOT fall through to sshd -- so a
refusal after this script is a policy gap, not a broken install. Do not debug
the machine for it.

  https://login.tailscale.com/admin/acls

  "ssh": [
    { "action": "check",
      "src":    ["autogroup:member"],
      "dst":    ["autogroup:self"],
      "users":  ["autogroup:nonroot", "root"] }
  ]

Still outstanding from before, and more important than it sounds:

  Disable key expiry for finch at
  https://login.tailscale.com/admin/machines

When a node key expires the machine drops off the tailnet silently, and that
disappearance looks IDENTICAL to the crash all of this was installed to
observe. It would be diagnosed as another hang.

=== VERIFY FROM gps3, NOT FROM HERE ===

Testing from finch proves nothing about reachability. From gps3:

    ssh finch                      # Tailscale SSH
    ssh finch@100.111.100.73       # openssh, over the tailnet
    nc -vz 100.111.100.73 22       # is anything listening at all
CLOSING
