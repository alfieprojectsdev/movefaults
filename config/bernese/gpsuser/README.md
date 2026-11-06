# Gold-standard `$U` (GPSUSER) configuration

This tree is meant to be the **source of truth** for everything PHIVOLCS-specific
in the Bernese user directory; see *Status* below for what is still missing from
it, and for how to restore what is here. `scripts/provision_gpsuser.py` copies it into `$U` (`~/GPSUSER`), sanitizing
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

**Stock Bernese panels and PCFs.** Apart from the files in this tree, `$U/OPT` and
`$U/PCF` on gps3 match the `$C/USER` template shipped with Bernese 5.4. Vendor files
belong to the vendor; committing 47 unmodified panel directories would bury the
handful of files we actually own. Only *our* additions and deltas go here. The two
`R2S_*` panels are whole files because `$U` needs a whole file, and each differs
from stock on one line.

---

## Status: restoring production, and what is still missing

**Production's PCFs, drivers and two changed panels are here since 2026-11-06**,
byte-identical to `$U` on gps3 that day. `PROVENANCE.md` lists them. Runs read the
copies in `$U`, not these.

**Restore them by copying, not with `--apply`.** The provisioner refuses this tree
today, so `--apply` writes nothing: `OPT/PGN_WK/` carries hardcoded dates, sessions
and campaign names, and the two `R2S_*` panels carry the stock panels' own dates
and sessions. Editing those panels to satisfy it would stop them matching what
production ran. On a machine with Bernese installed and `$U` populated from stock,
from the repository root:

```bash
T=config/bernese/gpsuser
cp -p "$T"/PCF/*.PCF "$U/PCF/"
cp -p "$T"/SCRIPT/* "$U/SCRIPT/"
cp -p "$T"/OPT/R2S_FIN/ADDNEQ2.INP "$U/OPT/R2S_FIN/"
cp -p "$T"/OPT/R2S_GEN/ADDNEQ2.INP "$U/OPT/R2S_GEN/"
```

**To see whether gps3 has drifted from this tree,** run the dry run below: `=` means
identical, for `SCRIPT/` and `PCF/`. It doesn't compare panels, so check those with
`cmp "$T"/OPT/R2S_FIN/ADDNEQ2.INP "$U"/OPT/R2S_FIN/ADDNEQ2.INP`, and the same for
`R2S_GEN`. A change made on the server still has to be copied back here by hand.

**This doesn't yet rebuild gps3 on its own.** Still outside this tree:

| Where | What it is |
|---|---|
| `$U/PAN/MENU_CMP.INP` | Lists the campaigns, hand-edited in August 2026. The provisioner doesn't handle it; add `${P}/<CAMPAIGN>` lines by hand |
| `$D/REF54` | The campaigns' `.STA`, `.CRD`, `.ABB`, `.BLQ` and `.ATL` files. Data, not configuration |

The PAGENET assets, `PCF/PAGENET_DLY.PCF` and `OPT/PGN_WK/`, were captured from the
T420 on 2026-08-03 (`4e82eaa`). They record what ran, so don't re-derive them.

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
