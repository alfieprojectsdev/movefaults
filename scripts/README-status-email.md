# Run-status notifications without an assistant session

`scripts/luzon_status.sh` prints the state of the LUZON reprocessing run. It is
plain bash and cron — it keeps working when every terminal is closed.

## Option A — check it over SSH (nothing to configure)

From any machine that can reach the R740, in an ordinary terminal:

```bash
ssh gps3@192.168.48.98 repos/movefaults_clean/scripts/luzon_status.sh
```

Live view, refreshing every five minutes:

```bash
watch -n 300 'ssh gps3@192.168.48.98 repos/movefaults_clean/scripts/luzon_status.sh'
```

**`watch` runs on YOUR machine**, not the server. It re-opens an SSH connection
each time and prints the result; the R740 is unaware of it. Ctrl-C stops it and
leaves the processing run untouched — the two share nothing.

**The IP rather than a hostname, deliberately.** `ssh gps3` works only where
`gps3` is defined — your `~/.ssh/config`, `/etc/hosts`, or DNS. That is true on
the T420 and false on a machine you borrow. `192.168.48.98` works from anywhere
on the PHIVOLCS network. If you prefer the short form, define it once:

```
# ~/.ssh/config
Host gps3
    HostName 192.168.48.98
    User gps3
```

then `ssh gps3 repos/movefaults_clean/scripts/luzon_status.sh` works on that
machine only.

The path is relative to the `gps3` home directory, which is where SSH starts —
no `cd` needed.

**Set up an SSH key** or `watch` prompts for a password every five minutes:

```bash
ssh-copy-id gps3@192.168.48.98
```

The **exit code carries the headline**, so it
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

### Which address goes where

`MAIL_FROM` is **not** free. Gmail binds it to the account you authenticate as:
set it to some other address and Gmail will either rewrite it back or reject
the message outright, as an anti-spoofing measure. It works only if that
address is already a verified *"Send mail as"* alias on the account.

`MAIL_TO` is free. Nothing constrains where mail is delivered.

So if you want a PHIVOLCS address involved, it goes on `MAIL_TO`:

```
MAIL_FROM=you@gmail.com          # must equal MAIL_USER
MAIL_USER=you@gmail.com          # the account holding the app password
MAIL_TO=you@phivolcs.dost.gov.ph # free
```

**Prefer the institutional address for `MAIL_TO`**, for the same reason the
runbooks and session logs are in git rather than someone's notes. A run report
landing in a personal mailbox is invisible to PHIVOLCS — if the person who set
it up is away or moves on, nobody else can see that a reprocessing ran, when,
or whether it failed. In the institutional inbox it is a record the
organisation holds.

**If PHIVOLCS runs Google Workspace** — many `.gov.ph` domains do — generate the
app password on the PHIVOLCS account instead and make all three fields
PHIVOLCS. Same `MAIL_URL`; Workspace uses the same SMTP endpoint. That is the
cleanest outcome, because nothing personal remains in the configuration. Worth
checking first: it is the same amount of work either way.

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

### Quieter alternative: only mail when something needs you

Every 30 minutes for a 13-hour run is 26 emails. To hear only about problems:

```cron
*/30 * * * * $HOME/repos/movefaults_clean/scripts/luzon_status.sh >/dev/null 2>&1 || $HOME/repos/movefaults_clean/scripts/luzon_status.sh --email >/dev/null 2>&1
```

**One line, however long.** Cron has no line continuation: a trailing `\` does
not join lines, so the next line is read as a new entry and rejected with
`bad minute`. An earlier version of this file wrapped that command across two
lines for readability and could not be installed.

The first call is silent on exit 0 and triggers the second only on **finished,
stalled, or driver-gone**. Recommended for an overnight run.

**Use one of the three cron forms above, not several.** They all fire on the
same `*/30` schedule, so keeping two means two status runs at once and, with
`--email` on both, two messages.

## Why not a mail server

`postfix`/`msmtp` would each need `sudo`, a package install, and a config file
holding the same credential. `curl` needs none of that and is already present.
The tradeoff: no queueing or retry, so a transient network failure means one
missed email rather than a delayed one. For a status ping that is the right
trade — the next one is thirty minutes away.
