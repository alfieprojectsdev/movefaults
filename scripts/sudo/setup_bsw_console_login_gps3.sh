#!/usr/bin/env bash
# setup_bsw_console_login_gps3.sh -- put a per-person login in front of the BSW
# console: Caddy on HTTPS, one username (initials) and random password each.
#
# --lan is gps3's own LAN address with its prefix length. It is an argument so that
# the address stays out of this public repository. The tailnet address is read from
# tailscale at run time.
#
# Run:      sudo bash /home/gps3/repos/movefaults_clean/scripts/sudo/setup_bsw_console_login_gps3.sh --users AB,CD,... --lan <address>/<prefix> > ~/bsw_console_login_setup.log 2>&1
# Add one:  sudo bash <same path> --add-user EF > ~/bsw_console_login_add.log 2>&1
# Undo:     sudo bash <same path> --undo --lan <address>/<prefix> > ~/bsw_console_login_undo.log 2>&1
#
# What it does:
#   1. Installs Caddy (Ubuntu's 2.6.2). It listens on 8443, HTTPS only, on the
#      LAN address and the tailnet address, nothing else; no port 80 redirect.
#      The certificate comes from Caddy's own local CA ("tls internal"); its
#      root certificate is copied to ~gps3/bsw_console_root_ca.crt, so each
#      browser can trust it once instead of clicking through a warning.
#   2. One login per person: initials and a random 16-character password,
#      stored only as bcrypt hashes in /etc/caddy/bsw_console_users. The
#      plaintext list goes to /root/bsw_console_credentials_<date>.txt (mode
#      600) for hand-out, the same way as field-ops' credentials; shred it after.
#   3. Caddy passes the signed-in name to the console as X-Remote-User, and
#      overwrites any X-Remote-User a browser sent.
#   4. The console moves to 127.0.0.1:8002 and trusts X-Remote-User only from
#      127.0.0.1, i.e. only from Caddy. Nothing on the network reaches it
#      without logging in.
#   5. Firewall: 8443 from the LAN and the tailnet; the old 8002 rules removed.
#
# What it does NOT do:
#   - switch on the stage 3 buttons. That is BSW_CONSOLE_ACTIONS=on plus
#     BSW_CONSOLE_OPERATORS in the console's unit, a separate step once the
#     run worker service is up and everyone can log in.
set -euo pipefail

TS_IF=tailscale0
PORT=8443
CONSOLE_PORT=8002
CONSOLE_UNIT=/etc/systemd/system/bsw-console-alpha.service
USERS_FILE=/etc/caddy/bsw_console_users
CADDYFILE=/etc/caddy/Caddyfile
CA_SRC=/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt
CA_OUT=/home/gps3/bsw_console_root_ca.crt
CREDS=/root/bsw_console_credentials_$(date +%Y%m%d).txt

[ "$(id -u)" -eq 0 ] || { echo "FATAL: run with sudo" >&2; exit 1; }
echo "== $(date -Is) $0 $*"

ACTION="" USERS_ARG="" ADD_USER="" LAN=""
while [ $# -gt 0 ]; do
  case "$1" in
    --users) ACTION=setup; USERS_ARG=${2:-}; shift 2 || shift ;;
    --add-user) ACTION=add; ADD_USER=${2:-}; shift 2 || shift ;;
    --undo) ACTION=undo; shift ;;
    --lan) LAN=${2:-}; shift 2 || shift ;;
    *) echo "FATAL: unknown argument $1" >&2; exit 1 ;;
  esac
done
[ -n "$ACTION" ] || { echo "FATAL: --users AB,CD,... --lan ADDRESS/PREFIX, --add-user INITIALS, or --undo --lan ADDRESS/PREFIX" >&2; exit 1; }

LAN_IP="" LAN_NET=""
if [ "$ACTION" != add ]; then
  [[ "$LAN" =~ ^[0-9.]+/[0-9]+$ ]] || { echo "FATAL: --lan takes this host's LAN address with its prefix length, ADDRESS/PREFIX" >&2; exit 1; }
  LAN_NET=$(python3 -c 'import ipaddress,sys; print(ipaddress.ip_interface(sys.argv[1]).network)' "$LAN") \
    || { echo "FATAL: --lan $LAN is not an address" >&2; exit 1; }
  LAN_IP=${LAN%/*}
  ip -4 -br addr show | grep -qF " $LAN_IP/" || { echo "FATAL: $LAN_IP is not on this host" >&2; exit 1; }
fi

console_on_lan() {  # undo: the console back on the LAN address, no proxy trusted
  sed -i "s|^Environment=BSW_CONSOLE_HOST=.*|Environment=BSW_CONSOLE_HOST=$LAN_IP|" "$CONSOLE_UNIT"
  sed -i '/^Environment=BSW_CONSOLE_TRUSTED_PROXIES=/d' "$CONSOLE_UNIT"
}

if [ "$ACTION" = undo ]; then
  systemctl disable --now caddy 2>&1 || true
  console_on_lan; systemctl daemon-reload; systemctl restart bsw-console-alpha
  ufw delete allow from "$LAN_NET" to any port "$PORT" proto tcp || true
  ufw delete allow in on "$TS_IF" to any port "$PORT" proto tcp || true
  ufw delete deny "$PORT"/tcp || true
  ufw allow from "$LAN_NET" to any port "$CONSOLE_PORT" proto tcp comment 'bsw-console alpha'
  ufw deny "$CONSOLE_PORT"/tcp comment 'bsw-console alpha: LAN only'
  echo "== undone: console back on http://$LAN_IP:$CONSOLE_PORT, Caddy stopped (package left installed)"
  exit 0
fi

new_user() {  # $1 = initials; appends the hash, prints "initials password"
  local u=$1 pw hash
  [[ "$u" =~ ^[A-Za-z0-9._-]{1,32}$ ]] || { echo "FATAL: bad username $u" >&2; exit 1; }
  grep -q "^$u " "$USERS_FILE" 2>/dev/null && { echo "FATAL: $u already exists" >&2; exit 1; }
  pw=$(python3 -c 'import secrets,string; a=string.ascii_letters+string.digits; print("".join(secrets.choice(a) for _ in range(16)))')
  hash=$(caddy hash-password --plaintext "$pw")
  echo "$u $hash" >> "$USERS_FILE"
  echo "$u $pw" >> "$CREDS"
}

if [ "$ACTION" = add ]; then
  [ -n "$ADD_USER" ] || { echo "FATAL: --add-user INITIALS" >&2; exit 1; }
  umask 077; new_user "$ADD_USER"; chown root:caddy "$USERS_FILE"; chmod 640 "$USERS_FILE"
  systemctl reload caddy
  echo "== added $ADD_USER; password is in $CREDS (root only). Shred it after hand-out."
  exit 0
fi

[ -n "$USERS_ARG" ] || { echo "FATAL: --users AB,CD,... (initials, comma-separated)" >&2; exit 1; }
IFS=',' read -r -a USERS <<< "$USERS_ARG"
[ -f "$USERS_FILE" ] && { echo "FATAL: $USERS_FILE exists; use --add-user, or --undo and remove it first" >&2; exit 1; }
TS_IP=$(tailscale ip -4 2>/dev/null | head -1)
[ -n "$TS_IP" ] || { echo "FATAL: no tailnet address" >&2; exit 1; }

echo "== install"
DEBIAN_FRONTEND=noninteractive apt-get install -y caddy >/dev/null
caddy version

echo "== users: ${USERS[*]}"
umask 077
: > "$USERS_FILE"
for u in "${USERS[@]}"; do new_user "$(echo "$u" | tr -d ' ')"; done
chown root:caddy "$USERS_FILE"; chmod 640 "$USERS_FILE"

[ -f "$CADDYFILE" ] && cp -n "$CADDYFILE" "$CADDYFILE.pre-bsw-console-$(date +%Y%m%d)"
cat > "$CADDYFILE" <<EOF
{
	auto_https disable_redirects
	skip_install_trust
}

https://$LAN_IP:$PORT, https://$TS_IP:$PORT {
	bind $LAN_IP $TS_IP
	tls internal
	basicauth {
		import $USERS_FILE
	}
	reverse_proxy 127.0.0.1:$CONSOLE_PORT {
		header_up X-Remote-User {http.auth.user.id}
	}
}
EOF
caddy validate --config "$CADDYFILE" --adapter caddyfile

echo "== console behind Caddy"
sed -i "s|^Environment=BSW_CONSOLE_HOST=.*|Environment=BSW_CONSOLE_HOST=127.0.0.1|" "$CONSOLE_UNIT"
grep -q '^Environment=BSW_CONSOLE_TRUSTED_PROXIES=' "$CONSOLE_UNIT" \
  || sed -i '/^Environment=PORT=/a Environment=BSW_CONSOLE_TRUSTED_PROXIES=127.0.0.1' "$CONSOLE_UNIT"
systemctl daemon-reload
systemctl restart bsw-console-alpha
systemctl enable caddy
systemctl restart caddy

echo "== firewall"
ufw allow from "$LAN_NET" to any port "$PORT" proto tcp comment 'bsw-console login'
ufw allow in on "$TS_IF" to any port "$PORT" proto tcp comment 'bsw-console login, tailnet'
ufw deny "$PORT"/tcp comment 'bsw-console login: LAN and tailnet only'
ufw delete allow from "$LAN_NET" to any port "$CONSOLE_PORT" proto tcp || true
ufw delete deny "$CONSOLE_PORT"/tcp || true

sleep 5
for i in $(seq 20); do [ -f "$CA_SRC" ] && break; sleep 1; done
cp "$CA_SRC" "$CA_OUT" && chown gps3:gps3 "$CA_OUT" && chmod 644 "$CA_OUT"

echo "== checks"
first=$(head -1 "$CREDS")
u=${first%% *}; pw=${first#* }
echo "no login     -> $(curl -sk -o /dev/null -w '%{http_code}' "https://$LAN_IP:$PORT/api/session") (want 401)"
sess=$(curl -sk -u "$u:$pw" "https://$LAN_IP:$PORT/api/session")
echo "as $u        -> $sess"
echo "$sess" | grep -q "\"user\":\"$u\"" || echo "WARNING: logged in as $u but the console says nobody is signed in: check the console runs with proxy_headers off (#338) and trusts 127.0.0.1"
echo "forged header-> $(curl -sk -u "$u:$pw" -H 'X-Remote-User: someone-else' "https://$LAN_IP:$PORT/api/session" | grep -o '"user":"[^"]*"') (want $u)"
echo "tailnet      -> $(curl -sk -o /dev/null -w '%{http_code}' -u "$u:$pw" "https://$TS_IP:$PORT/api/session") (want 200)"
echo "old http port-> $(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://$LAN_IP:$CONSOLE_PORT/api/session" || true) (want 000: not listening)"
ufw status | grep -E "$PORT|$CONSOLE_PORT" || true
echo "== done. Credentials: $CREDS (root only; hand out, then: sudo shred -u $CREDS)"
echo "== Root certificate for browsers: $CA_OUT"
