# Run-status notifications without an assistant session

`scripts/luzon_status.sh` prints the state of the LUZON reprocessing run. It is
plain bash and cron — it keeps working when every terminal is closed.

## Option A — check it over SSH (nothing to configure)

```bash
ssh gps3 repos/movefaults_clean/scripts/luzon_status.sh
```

Live view from your laptop, refreshing every five minutes:

```bash
watch -n 300 'ssh gps3 repos/movefaults_clean/scripts/luzon_status.sh'
```

An SSH key makes this painless. The **exit code carries the headline**, so it
can drive other things:

| code | meaning |
|---|---|
| 0 | running normally |
| 1 | finished |
| 2 | **stalled** — driver alive, no new solution in 45 min |
| 3 | driver gone with work outstanding |

Stall detection needs memory between runs, so the script keeps the last count
and timestamp in `~/.luzon_status_state`. From a single sample, "no progress"
and "a slow day" look identical.

## Option B — email every 30 minutes

`curl` sends the mail directly. **No mail server, no `sudo`, nothing to
install** — outbound SMTP was verified open from this machine on 2026-08-25.

### 1. Get an app password

Gmail will not accept your account password over SMTP. With 2-factor
authentication on, create an **App Password** at
<https://myaccount.google.com/apppasswords> — a 16-character string used only
by this script.

### 2. Write the config

```bash
cat > ~/.luzon_mail.conf <<'CONF'
MAIL_URL=smtps://smtp.gmail.com:465
MAIL_FROM=you@gmail.com
MAIL_TO=you@gmail.com
MAIL_USER=you@gmail.com
MAIL_PASS=abcdefghijklmnop
CONF
chmod 600 ~/.luzon_mail.conf
```

**This file holds a live credential.** It lives in `$HOME`, never in the
repository, and `chmod 600` is not optional. Anyone who reads it can send mail
as you. Revoke it from the same Google page when the run is over — an app
password left active for a finished job is a credential nobody is watching.

The script refuses to email if the file is missing, and says so, rather than
failing silently.

### 3. Schedule it

```bash
crontab -e
```

```cron
*/30 * * * * $HOME/repos/movefaults_clean/scripts/luzon_status.sh --email >/dev/null 2>&1
```

Cron survives logout and reboot. **An email failure never affects the run** —
the two are entirely separate processes.

**Start with this form for a first run.** Every thirty minutes is noisy, but
silence from the quieter form below is indistinguishable from a broken mail
setup — and you find out which at the moment you most wanted the alert. Run it
loud until a message has actually arrived, then switch.

### Quieter alternative: only mail when something needs you

Every 30 minutes for a 13-hour run is 26 emails. To hear only about problems:

```cron
*/30 * * * * $HOME/repos/movefaults_clean/scripts/luzon_status.sh >/dev/null 2>&1 || \
             $HOME/repos/movefaults_clean/scripts/luzon_status.sh --email >/dev/null 2>&1
```

The first call is silent on exit 0 and triggers the second only on **finished,
stalled, or driver-gone**. Good for an overnight run once delivery is proven —
not before, for the reason above.

Prove delivery by hand rather than waiting for cron:

```bash
scripts/luzon_status.sh --email
```

It prints `(emailed <address>)` on success and `(email FAILED …)` on failure,
and either way the processing run is untouched.

## Why not a mail server

`postfix`/`msmtp` would each need `sudo`, a package install, and a config file
holding the same credential. `curl` needs none of that and is already present.
The tradeoff: no queueing or retry, so a transient network failure means one
missed email rather than a delayed one. For a status ping that is the right
trade — the next one is thirty minutes away.
