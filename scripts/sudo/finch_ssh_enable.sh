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
# Captured once and matched with a here-string rather than `ss | grep -q`.
# Under `set -o pipefail` that idiom reports a FALSE NEGATIVE whenever the
# producer is still writing when grep exits on its match: grep -q returns 0,
# the producer takes SIGPIPE and exits 141, and pipefail promotes 141 to the
# pipeline's status. It happens to be safe here today because `ss` emits nine
# lines and finishes first -- but that is a property of this host's listener
# count, not of the code. `lsmod | grep -qi` in finch_watchdog_fix.sh had the
# same shape over 164 lines and could never return "yes".
LISTENERS=$(ss -lntp 2>/dev/null || true)
if grep -q ':22 ' <<<"$LISTENERS"; then
    grep ':22 ' <<<"$LISTENERS" | sed 's/^/  /'
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
    # `RunSSH` appears 0 times in `tailscale status --json` and once in
    # `tailscale debug prefs`, so the obvious check reads a document that has
    # never carried the field and returns false on a correctly configured host.
    # A check that CANNOT SUCCEED is a different defect from one that fails
    # noisily, and the two are indistinguishable in a diff.
    echo "  prefs: $(tailscale debug prefs 2>/dev/null | grep -i RunSSH | tr -d ' \t,' || echo 'RunSSH not found')"

    # The banner test belongs to a PEER, not to this host, and that is not a
    # style preference -- it is measurable:
    #
    #     from gps3   100.111.100.73:22  ->  SSH-2.0-Tailscale
    #     from finch  100.111.100.73:22  ->  SSH-2.0-OpenSSH_10.2p1 Debian-2
    #
    # Tailscale SSH intercepts INBOUND traffic from tailnet peers. A connection
    # from this host to its own tailnet address is not inbound peer traffic, so
    # it lands on the system sshd. Running the banner check here would report
    # "Tailscale SSH is not shadowing it" on a host where it demonstrably is --
    # the same shape as the two bugs above, in the check written to catch them.
    #
    # `head -n 1`, never `head -c N`: sshd sends its banner then waits for a
    # client that never speaks, so a byte count larger than the banner blocks
    # until `timeout` kills it, taking the buffered output with it. That is how
    # an earlier probe reported "nothing listening" against a healthy sshd.
    TS_IP=$(tailscale ip -4 2>/dev/null | head -n 1 || true)
    echo "  Tailscale SSH shadows port 22 on ${TS_IP:-the tailnet address} for"
    echo "  PEERS only; from here that port is the system sshd. Confirm from"
    echo "  another tailnet node -- it must answer SSH-2.0-Tailscale:"
    echo "      timeout 5 bash -c 'exec 3<>/dev/tcp/${TS_IP:-<tailnet-ip>}/22 && head -n 1 <&3'"
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
