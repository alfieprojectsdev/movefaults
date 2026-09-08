# T420 session log — 2026-09-08

**Why this file is separate from `docs/gps3-sessions/`.** That log is the R740
session's record, written by that machine for this one. Same reasoning as
`config/bernese/gpsuser52-luzon/PROVENANCE.md`: relay corrections, do not
commit into another session's file. This session reviewed gps3's log as PR #191
rather than editing it.

**Machine:** T420. **Counterpart:** R740 (gps3), reachable and reviewing.

---

## 1. The cross-review protocol, and why it was needed

The user established it mid-session: **whoever opened a PR merges or closes it,
acting on review comments from the other machine.** Neither session merges the
other's work.

It closes a gap in `§5` of `GPS3_COORDINATION_ONBOARDING.md`, which assigned
ownership per file and said nothing about who lands a PR. The default that
filled the silence was *whoever notices it is green*, and under it gps3 merged
#178, #181, #183 and #184 — all opened here.

The case that argues for the rule is **#178**: the reviewing session found a
placement problem, tried to fix it on a branch it did not own, **the fix failed
silently, and the PR merged wrong anyway.** A reviewer who can merge is tempted
to fix rather than report, and a fix pushed to someone else's branch is
invisible to its author until it has landed.

Written up as `§5a` in PR #192, because `§5` assigns that file to this machine.

### Green checks are not a review here, and that is now written down

CodeRabbit declines this repo — *"manual review required for this OSS
repository"* — and skips stacked PRs entirely. An all-green check list means
the automation abstained. So a review that finds nothing still says so on the
PR, because "reviewed, no findings" and "nobody looked" otherwise render
identically.

### What the first three cross-reviews caught

None are syntax. None would have been caught by reading:

| finding | shape |
|---|---|
| a site count **wrong at every catalog revision** (54 → 60) | drift was the natural explanation and the wrong one |
| an inflation figure **counting files outside the walk root** (494 → 213) | the walk never read them |
| a property attributed to **teqc** | really a property of 781 particular files |

That sets the standard: reviewing here means re-running the measurement, not
reading for plausibility.

---

## 2. Reviewing gps3's #191 — the identification was right, the numbers were not

§30.13 identified 494 `.crx` on gps3 as Bernese satellite problem files rather
than Hatanaka RINEX 3, and checked the blast radius on the counterpart matching.

**The identification holds.** Applying the section's own closing standard —
*the magic bytes are the fact* — to its own claim:

```
magic bytes, .crx under /srv/gnss-archive
    205  SATE
      6  POSS
```

**The count does not.** There are 254 on the whole machine, and they straddle
the boundary the argument turns on:

```
213  /srv/gnss-archive   <- inside --root, in the stage-3 corpus
 41  /home/gps3          <- BERN54/GLOBAL/CONFIG, SUPGUI/DOC, GPSDATA*/DATAPOOL/REF54
```

So the inflation is at most **213 of 471,874, not 494**, and half the error was
counting files outside the walk root as though the walk had read them — which
is a close cousin of the failure the section is about. Two smaller ones: 471,878
should be 471,874, and the figure stage 3 inflates is the attribution headline
**89.3%**, not the 94.4% counterparts figure quoted beside it.

**The load-bearing half was correct and verified.**
`raw_rinex_counterparts.py:48` is
`^([A-Za-z0-9]{4})(\d{3})[a-z0-9]?\.(\d{2})[od]$` — `.CRX` cannot match it, so
the 94.4% and the 2,060 are genuinely untouched.

---

## 3. `_RAW` has no `.dat`, and that is the whole decode story

Last night's decode was predicted to close 16 site-years and closed **4**. The
explanation is one missing alternative in one regex.

`want_list_diff.py` counts a site-year as covered if it sees raw matching
`_RAW = \.(t0[0-9]|tgd|m[0-9]{2})$`. **No `.dat`.** So:

- twelve of the sixteen were **already closed** by #184's grandparent-year fix,
  which reads `.t0x`/`.mNN` raw directly and had landed between the overlap
  analysis and the decode run;
- the only four that *could* newly close — `CCA5`, `ITGN`, `LAG1`, `NV47` — are
  exactly the four whose raw is `.dat`.

Perfect consistency, and the decode's entire yield sat inside a disagreement
between two scripts about whether `.dat` counts as raw.

**Want-list: 347 of 954 site-years closed across 175 sites**, up from 343.

Decode totals: 3,869 decoded ok, 2 rejected by the epoch guard, 113 conversion
failures, 2,977 files on disk — 892 lost to the `SSSSDDD0.YYo` filename
collision, documented as a known limitation in #189.

**The epoch guard earned its place.** Both rejections were genuine filing
errors, not decode failures: `LUZC050a.m01` sitting in `RAW/2012/` while
containing 2011 data. A silently wrong year is the failure mode that corrupts
want-list matching in exactly the way hardest to notice, because the file looks
fine.

---

## 4. `rsync --dry-run` without `-v` prints nothing at all

Every "0 outstanding" verification this session made using that pattern was
counting an empty stream. Four transfers were verified that way.

What saves it is that each was **also** verified by per-extension count
comparison, drive against gps3. **DATA0 is the proof the second method was
doing real work:** the count check caught 5 `.rar` (442 MB, VCAC Valenzuela
2016) that the vacuous rsync reported as fine.

This is the same failure as `systemd-modules-load` exiting 0 on a deny-listed
module and as the port-22 banner grab — **a tool silent by default reports
success by producing no output**, and piping it to `wc -l` turns that silence
into something that looks like a measurement.

The three differ in how they are fixed, which is worth separating: `rsync` has
a flag (`-v`), `systemd-modules-load` has an exit code that is simply wrong and
needs an independent check (`test -e /dev/watchdog`), and the banner grab had
neither.

---

## 5. DC9A88 — "stock Bernese only" was wrong

The verdict was true of the 64 files examined and false of the partition.
`Users/Decollement/Desktop/ToLizeth/` held **eight RINEX closing four
want-list site-years** — BACO, BULA, NAUJ and PUER, all 2013, none covered by
any other drive.

Generalised from the directories that were recognised. Checking where the data
is expected to be, rather than everywhere.

---

## 6. WVFS — the single-frequency network, and whether its results are usable

The user's standing question: the West Valley Fault System network's vectors
have no trend, the NCKU knowledge transfer was not absorbed, and nobody has
known whether the processing output is usable.

**It is not, and the reason is not the processing.**
`toto_D/programs from NCKU/Profile/velocity/NONE/fit-h.out` is the only velocity
output in the archive. Not one site reaches 2σ. Three are below 0.4σ —
indistinguishable from zero. The two largest, MALY (+31.5) and TUNA (−31.6),
sit at ~1.9σ and point in opposite directions.

So "the vectors have no trend" is the correct reading. There is no trend to see
because **the velocities are not resolved**. Any map of them is a map of the
noise. That is a result about the data, not a failure of understanding on
anyone's part.

Three corrections came from gps3's review of the write-up (#190):

- **60 NCR sites, not 54.** The natural explanation — the catalog was
  regenerated twice that day — is wrong: the box test returns 60 at *every*
  revision back to `cec8631`, and no filter reproduces 54 (non-ambiguous gives
  50). It was never a number this catalog produces.
- **RGMH matched at 4,234 m** where every other identification is 4–18 m. Two
  orders of magnitude worse is a proximity, not an identification; printing it
  in the same column let it borrow credibility the sub-20 m rows had earned.
  Now marked unidentified, with the velocity kept — dropping the row would
  quietly improve the sample by removing a measurement.
- **`SOLD` matches a cluster, not the catalog row**, and the consequence had
  been missed.

### The SOLD collision, and what it costs

`crd_catalog.csv` gives `SOLD` one representative coordinate and it is the
**Leyte** one: 11.0339 N, 125.7407 E, `ambiguous=yes`, `n_clusters=2`,
`cluster_extent_m=631866.9`. The NCR monument is the second cluster, at
14.40085 N 121.03742 E — **Soldiers Hills Village, Putatan, Muntinlupa**, which
is NCKU's site `9875`, and a neighbour of `MUNT`.

The consequence: **`SOLD` is not one of the 60.** The box test reads the
representative coordinate and that coordinate is in Samar. A site is excluded
from its own network's count by a code collision with a monument 632 km away.

`PHIVOLCS_single/wvfs/` looks like the missing piece and is not — it is
Taiwanese data. `MOQC` and `MESA`, named from institutional memory, appear in
no catalog. The KMZ catalogs (2017, 2018, 2023) contain `SOLD` **only** at
Leyte; neither the Muntinlupa `SOLD` nor `CENT` appears in any of them.

---

## 7. finch hardening — what is armed and what is not

**§30.5 of the gps3 log was wrong and #191 corrects it.** The hardware watchdog
is **not armed**: `iTCO_wdt` is deny-listed by the distribution,
`systemd-modules-load` honours the deny-list **while exiting 0**, and
`RuntimeWatchdogUSec` was set on a device that does not exist. Confirmed here
independently.

So the discriminator between "wedged" and "power loss" does not yet exist, and
any crash before it does is as ambiguous as the previous three.

| item | state |
|---|---|
| sysrq bitmask (438 → 1) | script written, **unrun** |
| `iTCO_wdt` via direct `/sbin/modprobe` | script written, **unrun** |
| wifi: stop dropping WLAN when RJ45 is up | script written, **unrun** |
| pstore / `efi_pstore` | armed and empty — **eliminates kernel panic** |
| hibernation as crash cause | **eliminated, with a control** |

**The hibernation elimination is the one worth keeping as a method.** Seven
boot-time `PM: hibernation: Registered nosave` lines per log prove the PM
subsystem was logging in all three captures. Zero entry events against a
demonstrably live logger is a real negative — the same standard pstore
supplied, applied without being asked for.

Eliminated as *history*, not as *mechanism*: `upower`'s critical action is
`HybridSleep` and fires unasked, and at 16.9% of design capacity this battery
reaches critical fast. That is configuration to change, not something to
instrument.

The watchdog workaround calls `/sbin/modprobe` directly, which the deny-list
does not block — `systemd-modules-load` honours it, an explicit `modprobe` does
not.

---

## 8. Landed

| PR | what |
|---|---|
| #184 | `want_list_diff.py` grandparent-year support — 332→339 local, 330→338 on the gps3 archive |
| #189 | `decode_raw_gap.py`, plus the review round: corpus named, `fixdatweek` claim scoped, tool preflight, `E741` |
| #190 | WVFS usability, plus the review round: 60 sites, RGMH unidentified, SOLD cluster note |
| #192 | `§5a` cross-review protocol — open, for gps3 to review |
| #191 | gps3's session log — reviewed here, gps3 to merge |

`main` advanced and was verified after each merge, per branching rule 5.

---

## 9. Not done

- 113 decode conversion failures, uninvestigated.
- Three finch hardening scripts still unrun (§7) — each needs a tty this
  session does not have, and is handed over by absolute path.
- Tailnet ACL `ssh` block and key-expiry disable, both in the Tailscale admin
  console.
- The main worktree still carries three unresolved merge conflicts
  (`docs/SETTLED.md`, `docs/bern52/rinex_attribution.md`,
  `scripts/match_rinex_to_site.py`); `git merge --abort` is gated. Work this
  session was done in `.trees/` worktrees, which are clean.
- `feat/crd-catalog-clusters` — per-cluster catalog output, started, not
  finished. `SOLD` is the argument for it: a row with two clusters 632 km apart
  cannot be represented by one coordinate, and §6 shows what that costs.
