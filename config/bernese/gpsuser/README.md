# Gold-standard `$U` (GPSUSER) configuration

This tree is meant to be the **source of truth** for everything PHIVOLCS-specific
in the Bernese user directory; see *Status* below for what is still missing from
it. `scripts/provision_gpsuser.py` copies it into `$U` (`~/GPSUSER`), sanitizing
on the way. Readiness task **P1-H**.

**Never hand-edit `$U` directly.** Edit here, commit, re-provision. That is the
whole point of the tree existing.

---

## Why this exists

Two reasons, and the second is the operational one.

**Reproducibility.** The MIS team reconfigures the production server. When they
do, a working Bernese environment has to be recoverable by re-running
provisioning — not by someone re-debugging panels by hand from memory. Nothing
here should be recoverable *only* from a running machine.

**Panels do not survive travel.** Every panel that came off a Windows Bernese
install carried problems into the Linux run: `\` path separators taken as
literal characters, a dangling `WAIT=522` that would have hung the BPE on a PID
that no longer existed, and hardcoded session/campaign literals from the
instructor's demo week. The provisioner catches all three classes on the way
out, so they cannot reach `$U` again.

---

## Layout

Mirrors `$U`'s own structure. Anything placed here lands at the same relative
path under `~/GPSUSER`.

```
SCRIPT/     Perl drivers. Copied VERBATIM — a backslash in Perl is an escape,
            not a path separator, so separator conversion would corrupt them.
PCF/        Process Control Files. Checked for dangling WAIT references
            before copying; a dangling WAIT blocks the BPE forever.
OPT/        Panel directories (*.INP). Separator-sanitized, and ADDNEQ2.INP
            gets MAXPAR sized from the station count.
```

### What is deliberately NOT here

**`PAN/USER.CPU`** — host-specific. `maxjobs` must track the *physical* core
count of whichever machine is running (the BPE sub-solves are FPU-bound, so
hyperthreads do not help and oversubscription is slower than a correct value).
Versioning it would carry one machine's core count onto another — exactly the
bug found on gps3 on 2026-08-03, where `USER.CPU` still read `maxjobs 2` from
the T420 and the 12-core R740 was using two of its cores. The provisioner
**generates** this file from the detected hardware instead.

**Stock Bernese panels and PCFs.** Apart from the files listed under *Status*,
`$U/OPT` and `$U/PCF` on gps3 match the `$C/USER` template shipped with Bernese
5.4. Vendor files belong to the vendor; committing 47 unmodified panel directories
would bury the handful of files we actually own. Only *our* additions and deltas
go here.

---

## Status: what this tree does not hold yet

**The environment can't yet be rebuilt from this tree alone.** These exist only
in `$U` on gps3, and re-running the provisioner would not restore them:

| On gps3 | What it is |
|---|---|
| `PCF/LUZON_DLY.PCF`, `LZFLT_DLY.PCF`, `PHREF_DLY.PCF`, `PHDEN_DLY.PCF` | The PCFs production and the console use. `scripts/derive_luzon_pcf.py --frame i20` generates the live `LUZON_DLY` from stock; its default, `i14`, does not |
| `PCF/PHNAT_DLY.PCF`, `PHRCTL_DLY.PCF`, `PHRPAR_DLY.PCF` | PCFs for trial and comparison runs |
| `SCRIPT/phden_pcs.pl`, `phnat_year.pl`, `LZFLT_DLY_pcs.pl`, `luzon_par.pl` | Perl drivers whose default PCFs are `PHDEN_DLY`, `PHNAT_DLY`, and `LUZON_DLY` for the last two |
| `OPT/R2S_FIN/ADDNEQ2.INP` | Stock, except `MAXPAR` 6000 (stock 1000). Edited on the server, backups beside it |
| `OPT/R2S_GEN/ADDNEQ2.INP` | Stock, except `MAXPAR` 4000 (stock 1000). Edited on the server, backup beside it |

Those two panel edits broke the rule at the top of this file. What this tree does
hold is the other drivers in `SCRIPT/` and the PAGENET assets: `PCF/PAGENET_DLY.PCF`
and `OPT/PGN_WK/`, captured from the T420 on 2026-08-03 (`4e82eaa`). They record
what ran, so don't re-derive them. `PROVENANCE.md` describes them.

**`--apply` refuses this tree today.** `OPT/PGN_WK/` still carries hardcoded dates,
sessions and campaign names, so the strict check aborts the whole run before
writing anything, and `OPT/PGN_WK/` is not in `$U` on gps3. The dry run below lists
every line it objects to; remap those before applying. The refusal is the tool
working, not a malfunction.

---

## Usage

```bash
# Show what would change. Default — writes nothing.
uv run python scripts/provision_gpsuser.py

# Apply, sizing ADDNEQ2 MAXPAR for a 72-station network
uv run python scripts/provision_gpsuser.py --apply --stations 72
```

The provisioner is **strict by default**: a panel carrying a hazard it cannot
safely auto-fix aborts the whole run before anything is written, so `$U` is
never left half-updated.
