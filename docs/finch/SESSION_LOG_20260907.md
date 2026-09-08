# Session Log — 2026-09-07 (T420 / finch)

**Machine:** T420 `t420`, Linux Mint 22.3 "zena"
**Scope:** finish evacuating the legacy drives, diagnose finch's outage, put it
on the tailnet, and get the evidence off the machine before it crashes again.

Written at 19:39 rather than at the end of the evening, deliberately: finch
ends 6 of its last 9 boots by losing power, and after today nobody is in the
building to restart it. A log scheduled for later is a log that may not exist.

---

## 1. Why finch was unreachable 2026-09-04 → 09-07

**Abrupt loss at 2026-09-04 01:20:56. No preceding error logged.** A day
earlier than the reported window.

The journal stops mid-normal-activity — per-minute timers fire, complete, then
nothing. No `Stopping …`, no `Reached target Shutdown`. `last -x` independently
records `crash`.

One trap worth naming: that boot *does* contain three `Reached target
shutdown.target` lines. They are **user-session** managers (`systemd[1503]`,
`[20703]`, `[105116]`) exiting hours earlier. A grep for the string alone
concludes "clean shutdown" and is wrong.

Ruled out with evidence, not assumption:

| hypothesis | why not |
|---|---|
| software shutdown | no shutdown sequence at all |
| thermal | all 17 `thermal` lines are boot-time driver registration; THM0 54 °C at boot |
| OOM | `earlyoom` logged 76.5 % memory free 45 min before |
| panic / MCE / hardware | zero matches |
| USB or disk wedge | zero disconnects, resets or I/O errors |

**Cannot determine** power loss vs PSU vs wedged kernel — all three produce
this signature. Saying which would be invention.

**The recurrence is the real finding.** Six of the last nine boots ended
abruptly; the three clean ones are the three shortest (17 m, 27 m, 2 h —
deliberate reboots). Every long unattended run has died. `wtmp` holds 156
crash records.

### A hypothesis chased and rejected

`udisksd` logged a SMART housekeeping failure every ~10 min for the whole boot,
77 times, against the GPS_1TB_2 drive attached at the time. Rejected: steady
cadence with no change approaching the failure, and zero USB disconnects, ATA
resets or I/O errors. A USB bridge that will not pass ATA passthrough. Noted in
case a future crash correlates with that drive.

### What this argues for

The watchdog in the headless-hardening playbook (#170) is not only recovery —
it is the **missing instrument**. The journal cannot separate a hang from a
power loss because the machine dies before it can write, and no further reading
of those logs will fix that. A watchdog discriminates: fires means hang, gone
without firing means power.

---

## 2. Two independent causes, one symptom

gps3 swept `192.168.48.0/24`, did not find finch, and read that as "powered
off". Both halves were true and neither alone explains it.

`/etc/NetworkManager/dispatcher.d/99-wifi-auto-toggle.sh` ran
`nmcli radio wifi off` whenever `enp0s25` came up — a **radio kill**, not a
route preference. finch's `192.168.48.x` address is on wifi, so whenever
ethernet was up finch was **not on the swept subnet at all**.

Fix written to `scripts/sudo/wifi_keep_both_networks.sh` (removes the hook's
execute bit; reversible with `chmod +x`). Not yet run.

---

## 3. Tailscale — finch is on the tailnet

`100.111.100.73`, `tailscaled` active, `tailscale ping gps3` → pong via
`192.168.48.98:41641` in 76 ms, **direct**. ssh over the tailnet works.

**The one thing that would have broken a copied recipe:** finch is Mint 22.3
"zena" and Tailscale publishes no `zena` suite —
`noble.noarmor.gpg` → 200, `zena.noarmor.gpg` → **404**. Reading
`VERSION_CODENAME` from `/etc/os-release`, the obvious implementation, installs
an apt source pointing at a 404, which breaks *every later* `apt update`. The
script reads `DISTRIB_CODENAME` from `/etc/upstream-release/lsb-release` and
curl-checks the URL **before** writing any source.

Two predictions in that script were wrong and were corrected against the
observed run rather than left standing: finch reports `UDP: true` and peers
directly, where gps3 reports `UDP: false` and relays. finch is **dual-homed** —
`enp0s25` on 192.168.40.x carries the default route, `wlp3s0` sits on
192.168.48.x, the same LAN as gps3. The direct peering is subnet-local, not
hole-punched. gps3's DERP finding is true of its own egress and is not a
site-wide property.

PR #175. Also fixed a hardcoded `TS_HOSTNAME="finch"` — gps3 proposed adopting
the script for both machines believing it took a hostname; it did not, and
doing so would have enrolled gps3 as a second node named `finch`.

---

## 4. Drives — all four fully evacuated

| drive | state |
|---|---|
| HD-LBU2 (WD20EARS, WCAZA4430660) | **complete** — 176,407 files / 142 GB |
| GPS_1TB_2 (WD10EARS, WCAV5M032380) | complete |
| DATA0 (Seagate W2A0W9T2) | complete |
| DC9A88 | nothing to take — Bernese 5.0 stock files only (`EXAMPLE.*`, `IGS_00`, `IGS_97`) |

**Three gaps found and closed today**, all on HD-LBU2:

- **16,483 observation files** in formats never on any extension list —
  `.CZO` 4,221, `.CZH` 4,221, `.PSO` 4,021, `.PSH` 4,020 — 4.8 GB, sitting in
  the *same* 1990s campaign `OBS/` directories as the `.PZO` already taken, and
  reading **zero** on gps3.
- 15,698 files of `.PZO`/`.PZH` + `.rar` (15.6 GB) — original-format campaign
  observations across 246 sites, and 7,119 rar with RINEX-shaped names.
- 29,836 processing logs (`.out`/`.prt`/`.log`/`.run`/`.sum`, 1.8 GB), earlier
  dismissed as low value; they are the provenance of how the solutions were
  produced.

~21 GB across three passes. Every GNSS and Bernese extension now matches the
drive count exactly. **The drives can stay at PHIVOLCS permanently.**

For the want-list none of this closes anything new — checked on site-**year**,
not site: the 300 entries `.PZO` would close are already closed by RINEX. It is
archival insurance on original formats, not a gap. An earlier claim of mine that
the drives "definitely could not come out" was based on site-level overlap and
was wrong.

Non-GNSS deliberately left behind: 38 k `.m` (MATLAB toolbox), 27 k `.jpg`,
15 k `.p`, 10 k `.pdf`, 4.5 k `.ppt`.

---

## 5. Crash evidence committed — and the two ways it nearly failed

`docs/finch/` now carries the two boot journals gzipped plus the diagnosis
(240 KB). PR #176.

**It is redacted, because this repository is public.** The journals carry two
family members' account names across 11,644 lines, alongside the screen-time
service run against them, plus the wifi SSID and seven MAC addresses.

Two failures worth recording, because both looked like success:

1. **A credential-only scan passes these files cleanly.** Every
   `password`/`secret`/`token` match is a systemd or NetworkManager unit
   *name* — "Forward Password Requests to Wall" — never a value. Nothing would
   have prompted the scan that actually mattered, which was for personal data.

2. **The first push silently dropped both journals.** `.gitignore:38` is
   `*.gz`; `git add` skips an ignored file **without warning**, and commit and
   push both exited 0. `git status` does not list an ignored file as missing.
   I "verified" with `ls -la` — of the working tree, which was never in doubt.
   gps3 caught it by running `git ls-tree` against the *pushed branch*. Fixed
   with a `!docs/finch/*.gz` negation beside the existing archive-manifests
   exemption, and re-verified from the origin blobs: correct line counts, zero
   identifiers, final line intact.

The general rule, which this project already writes down and I applied to
merges but not here: **never trust an exit code for a filtered operation —
confirm the remote state changed.**

Unredacted originals stay on finch with `~/README_finch_journals.md` beside
them explaining why they must not be committed. User approved the redaction.

---

## 6. Coordination with gps3

`SendMessage` is now the standing channel, alongside `gh pr comment` for
PR-scoped items and rsync'd md5-verified markdown for briefs. The delivery
status must always be reported: the tool returns "accepted … but delivery is
not confirmed", which is not success.

Two collisions surfaced, and one is instructive:

- Both machines wrote a Tailscale installer —
  `scripts/sudo/tailscale_setup.sh` here, `setup_tailscale.sh` there. Same
  directory, same job, transposed names. **They would have merged cleanly** —
  no conflict, no warning — leaving two installers to drift until somebody
  edited the wrong one. A collision check that looks only for merge conflicts
  cannot see this. gps3 dropped its branch.
- Both fixed stage 3's glob defect independently. gps3's regex is strictly
  better: mine lacked `re.I` and missed 27,293 lowercase `.z` files
  (471,874 vs 444,590). Mine dropped.

---

## 7. State at close

**Open PRs:** #170 headless playbook · #171 stage 4 · #173 doc audit ·
#174 CORS remote access · #175 tailscale · #176 crash evidence.
None reviewed. gps3's `docs/coordination-sendmessage-sop` branch also awaits
review under T420 ownership.

**Not done, deferred by agreement — all recoverable if finch crashes:**

- `openssh-server` script. Mint ships no sshd, so ssh works finch → gps3 but
  not back. Enable `ssh.socket` rather than `ssh.service` if Mint follows
  Debian's socket activation, or the unit reads `inactive` and looks broken.
- The watchdog-as-instrument paragraph for #170.
- `~/drive-arch-runs` (315 MB) — the drive walks. Regenerable **only** by
  re-docking all four drives, which stops being possible now the laptop has
  left. `all_HD-LBU2.txt` is the piece gps3 needs to independently reproduce
  the 259/271 want-list figure; without it that number has one measurement.
- Raw-vs-RINEX counterpart counts — gps3 has taken this, reporting two numbers
  (evidence and inference) rather than one.

**Unrun on finch:** `sudo bash /home/finch/wifi_fix.sh`.

**Still pending on the Tailscale admin console:** disable key expiry for
`finch`. When a node key expires the machine drops off silently, and that
disappearance looks *identical* to the crash this was installed to observe.

**Tier 2 single-copy work, surfaced not decided** (crosses project
boundaries): `webdevportfolio_ap` is 6 commits ahead of origin, and
`brewingbae-server`, `landingpage`, `Project-AdsBot`, `tawag-tugon-api` and
`lite-xl` have branches with no upstream at all.
