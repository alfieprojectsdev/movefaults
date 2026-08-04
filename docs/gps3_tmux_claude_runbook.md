# Running Claude Code on gps3 (Dell R740) under tmux

**Audience:** anyone with an account on gps3 — including whoever inherits this
system. Assumes no prior tmux knowledge.

**Why this document exists.** On 2026-07-30 a working session was run *outside*
tmux. When the laptop left the network, the SSH connection dropped and the
session ended with it. Nothing was lost that time because nothing was running —
but the archive transfer still ahead of us is hours of `rsync` from a failing
external drive, and losing that midway is expensive. tmux makes the difference
between "my laptop closed" and "the work stopped."

---

## 1. The one rule

**Start `tmux` FIRST, then start work inside it.**

A process already running in a plain SSH session **cannot be moved into tmux
afterwards**. If you forget, you have to stop and restart the work. There is no
retrofit.

```bash
ssh gps3
tmux new -s claude          # 1. create the session
claude                      # 2. THEN start Claude Code, inside it
```

---

## 2. Daily use

| Action | Command |
|---|---|
| Start a new named session | `tmux new -s claude` |
| **Detach** (leave it running) | Press `Ctrl-b`, release, then press `d` |
| Reattach later | `tmux attach -t claude` |
| List sessions | `tmux ls` |
| Attach if exists, else create | `tmux new -A -s claude` |
| Kill a session you're done with | `tmux kill-session -t claude` |

`Ctrl-b` is the tmux *prefix*: hold Ctrl, press `b`, **release both**, then
press the next key. It is not a chord — `Ctrl-b-d` pressed together does not
work.

Detaching is safe and instant. Everything inside keeps running with no terminal
attached. You can close the laptop, lose wifi, or fly somewhere; the work
continues on the server.

`tmux new -A -s claude` is the one to memorise if you only keep one: it attaches
to `claude` if it exists and creates it if it doesn't, so it is always correct.

---

## 3. Resuming a Claude Code conversation

Two independent things persist, and it helps to keep them straight:

- **The tmux session** lives on gps3 and holds the *running process*.
- **The conversation** lives on Anthropic's servers and holds the *history*.

So a conversation can be resumed even if tmux died:

```bash
claude --resume                     # interactive picker of recent sessions
claude --resume <session-id>        # jump straight to a known one
claude --continue                   # most recent conversation in this directory
```

The session id appears in the Claude Code UI and in the transcript path under
`~/.claude/projects/`. Record it in your session log when you stop for the day —
it costs one line and saves hunting later.

---

## 4. What survives what

| Event | tmux session | Claude conversation | Remote control |
|---|---|---|---|
| SSH drops / wifi lost | **Survives** | **Survives** | **Survives** |
| Laptop closed or shut down | **Survives** | **Survives** | **Survives** |
| You detach with `Ctrl-b d` | **Survives** | **Survives** | **Survives** |
| You close the SSH window | **Survives** | **Survives** | **Survives** |
| You type `exit` in the shell | Ends | Survives (`--resume`) | Ends with the process |
| **gps3 reboots** | **Destroyed** | Survives (`--resume`) | **Destroyed** |

**The remote-control column is measured, not assumed** (2026-08-03), in two
stages:

1. **SSH window closed, same network.** `tmux list-clients` returned **no
   attached clients**, yet the session still executed commands and answered
   normally. Confirmed as continuation rather than restart by PID — the process
   kept its original number (415338) with an uptime matching the tmux session's
   creation time.
2. **Reconnected from a home network, entirely outside the PHIVOLCS LAN.** The
   same session remained drivable with no VPN and no inbound port.

The second result is the operationally important one. **A long job on gps3 can
be started at the office and supervised from home** — which is the difference
between the archive transfer being a single unattended run and being something
that has to be babysat on site.

Why it works without any firewall change: gps3 makes an **outbound** connection.
Nothing listens for an inbound one, so this does not expose the machine to the
network it is reached from. The corollary is worth stating plainly: anyone with
access to the Claude account can drive this box, with whatever privileges the
session's user holds.

Caveat on the first test: a second SSH session from another host was still open.
The tmux session had zero attached clients either way, so the result holds, but
it was not clean-room. The second test did not depend on it.

**The reboot row is the one that catches people.** tmux keeps nothing on disk.
A kernel update or power event takes every session with it. Before a planned
reboot, stop long-running work deliberately rather than trusting tmux to carry
it through — it will not.

Note also that **system services do not need tmux at all.** The nightly git
mirror (cron, 22:37) and `smartd` run independently of any login session and
keep working while nobody is connected. tmux is only for *interactive* work you
started yourself.

---

## 5. Long transfers: the case tmux is actually for

For anything measured in hours — the legacy archive transfer especially — use a
**dedicated session per job**, not the one you're chatting in:

```bash
tmux new -s archive
rsync -av --info=progress2 <source>/ /srv/gnss-archive/legacy/
# Ctrl-b d to detach; check back whenever
```

Then reattach with `tmux attach -t archive` to see progress.

Run it inside tmux **on both ends** if the transfer is initiated from another
machine — a dropped SSH session kills the *client* side just as dead.

**Do not trust `rsync`'s exit code as proof the copy is complete.** rsync exits
0 having skipped files it could not read, and exits 23 on a run that copied
99.99% successfully. Verify with an independent census afterwards:

```bash
sudo -u gps3 /srv/gnss-archive/verify_archive.sh census
```

Compare files, symlinks, directories and bytes against the same census run on
the source. Symlinks are counted separately on purpose: this archive once lost
every symlink to a FAT32 intermediate hop, silently, and a file count alone
would not have noticed because the symlinks were still there as regular files.

---

## 6. Running `sudo` commands during a Claude Code session

Claude Code's shell has **no tty**, so it can never run `sudo` itself — the
password prompt has nowhere to appear. The established workflow on this box:

1. Keep a **second terminal** SSH'd into gps3 (its own tmux session is fine).
2. Claude writes the command as a script under
   `/home/gps3/repos/movefaults_clean/scripts/sudo/` and gives you the
   **absolute path only**.
3. You run that path with `sudo` in your terminal.
4. The script `tee`s its output to `scripts/sudo/logs/`, so you watch it live
   *and* Claude can read the result.

```bash
sudo /home/gps3/repos/movefaults_clean/scripts/sudo/<script>.sh
```

Nothing to transcribe between windows, no shell quoting to survive a
copy-paste, and no swallowed output. `scripts/sudo/logs/` is gitignored; **the
scripts themselves are committed**, because they are the record of what was
actually run on this machine.

---

## 7. If tmux is missing

```bash
sudo apt install tmux
```

It is already installed on gps3 as of 2026-08-03.

---

## 8. Quick reference

```
tmux new -A -s claude     start or reattach (the safe default)
Ctrl-b then d             detach, leaving everything running
tmux ls                   what sessions exist
tmux attach -t <name>     reattach to one
claude --resume           pick up a previous conversation

Start tmux BEFORE the work. A running process cannot be moved in later.
A reboot destroys every tmux session. Plan around it.
```
