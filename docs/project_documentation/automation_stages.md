# The three stages: what is automated, what is not, and what is worth automating

**Created 2026-08-13.** This is the tracking document for the workflow as the
analyst actually experiences it. Update it when a stage moves.

Every other status document in this repo is organised by *component* —
`roadmap.md` by dependency tier, `deliverables_tracker.md` by deliverable ID.
Those answer "what have we built?". This one answers a different question:
**how much of a human's working day have we actually removed?** The two do not
correlate as well as you would hope, and this document exists because we
repeatedly lost track of the second one while making progress on the first.

The stage boundaries come from PHIVOLCS' own `Work_Instruction_ao20251030.docx`
— they are the document's section structure, not a scheme invented here.

---

## Status at a glance

| Stage | Work instruction | What it does | Status |
|---|---|---|---|
| **1** | §4 | RAW → RINEX | ⏳ **Untouched** — Windows `.exe` + interactive Python |
| **2** | §5 | RINEX → coordinates | ✅ **Largely automated** (2026-08) |
| **3** | §6 | coordinates → velocities | 🔄 **Inverted** — the hard part is done, the plumbing is not |

**Stage 2 being the finished one is not a coincidence and not a plan.** It is
where the LUZON reprocessing forced us: a 31-day run had to work, so it was
made to work. The other two thirds were never chosen against — they were never
reached. Recognising that is the point of this document, because "we automated
the pipeline" is a claim that stage 2 alone does not support.

---

## Stage 1 — RAW → RINEX (§4)

**Status: untouched.** Nothing in this monorepo performs this stage.

### What it is today

Receiver-native binary (Trimble `.dat`/`.T0x`, Leica) → RINEX observation
files, with field metadata attached. Runs on Windows, driven by a mix of
`.bat` wrappers and interactive Python.

Snapshotted at `docs/bern52/phivolcs-scripts/rinex-conversion/`, plus
`rinex-checker/`, `s01r-hatanaka/`, `modify-igs-rinex3/` — **142 text
artifacts** in total, rescued off `\\192.168.48.99` on 2026-08-12. They were in
no version control before that.

### External dependencies, by frequency of reference

| Tool | References | Linux status |
|---|---|---|
| `teqc` | 2684 | Installed on gps3. **RINEX 2 only** — refuses RINEX 3 on line 1 |
| `runpkr00` | 777 | Trimble raw unpacker. **Not evaluated on Linux** |
| `gfzrnx` | 11 | Installed. Reads RINEX 3. Licence terms to be documented per use |
| `crx2rnx` / `rnx2crx` | 6 | Hatanaka compression. Trivially available on Linux |
| `campv5.exe`, `campv6.exe`, `campv5_mounted.exe`, `campv5_combine.exe` | — | Almost certainly PyInstaller builds of `campaign_v5.py`, `campaign_v6.py`, `campaign_v5_mounted.py`, `campaign_v5_combine.py` — the naming matches 4-for-4 and we hold the Python. **Verify before relying on it.** |
| `splname.exe`, `compress.exe` | — | **No source counterpart snapshotted.** Unidentified. |

### The real blocker is not the scripts

There are **52 files containing interactive `input()` prompts**. But porting
prompts to CLI flags is a weekend, and it would not buy much, because of what
the prompts are asking for:

```
    Site name:
    Antenna Type:  1 = TRM41249.00, 2 = TRM57971.00, 3 = TRM115000.00
    Average height:
```

**That is a human reading a paper field logsheet.** The bottleneck in stage 1
is not script execution, it is *getting field metadata into a machine-readable
form at all*. Automating the scripts around a human who is still typing antenna
heights off paper removes almost none of the working day, and adds a
transcription step that can now fail silently.

This is why `tech_spec_digital_logsheet.md` and the `field-ops` PWA matter more
to stage 1 than any script port. **The digital logsheet is the stage 1 unlock;
the script port is downstream of it.**

### Should we automate it?

**Not yet, and not as script porting.** In priority order:

1. **Verify the frozen `.exe`s are builds of the Python we hold.** This is a
   half-day and it either closes a succession risk or reveals one. Do it soon —
   it is cheap and the answer changes the plan.
2. **Identify `splname.exe` and `compress.exe`.** Same argument.
3. **Evaluate `runpkr00` on Linux.** It is the one hard dependency with no
   known substitute; if it does not run, stage 1 cannot leave Windows at all
   and that fact should be known now rather than discovered later.
4. **Then** the digital logsheet, **then** the script port.

---

## Stage 2 — RINEX → coordinates (§5)

**Status: largely automated.** This is the stage the LUZON reprocessing forced.

### What works, with evidence

| Capability | Evidence |
|---|---|
| Campaign staging (RINEX 2 + 3) | `scripts/stage_luzon_campaign.sh` |
| IGS/CODE product fetch | `scripts/fetch_igs_products.sh` (AIUB FTP firewalled; SWITCH S3 mirror) |
| Ocean loading | `scripts/merge_blq.py` |
| PCF derivation from 5.4 stock | `scripts/derive_luzon_pcf.py` — refuses dangling WAITs |
| Month-long unattended run | `scripts/run_luzon_month.sh` — **30/30 days, 2h47m** |
| Parallel multi-session | `REPR_MODE` — **5/5 sessions, 16m51s, byte-identical to sequential baseline** |
| Precision QC | `scripts/coord_repeatability.py` — median N 2.8 / E 3.0 / U 10.9 mm |
| Multi-station coherence | `scripts/network_coherence_scan.py` — found DOY 126 (14 stations) that single-station thresholds missed |
| Run comparison | `scripts/compare_solutions.sh` |
| Real BPE invocation from the service | `services/bernese-workflow/src/bernese_workflow/backends.py` via `startBPE.pm` |

### What is not done

- **Production still runs through `scripts/`, not `services/bernese-workflow`.**
  The service has 198 passing tests and genuinely invokes BSW — but no
  month-long run has gone through it. Migration is the standing direction, not
  a completed one. This is the single most misreported fact in the project's
  history: the service sat listed at "~10% complete" for months while carrying
  those tests.
- **No solution reaches TimescaleDB.** Steps 2–3 of the designed flow are
  aspirational; the ingestion pipeline is not in the loop.
- **RINEX QC is teqc-based and therefore RINEX 2 only**, with a gfzrnx fallback
  added 2026-08-13 (PR #80). Every IGS fiducial is RINEX 3.

### Should we go further?

**Yes, and the next step is specific: run one production month through
`services/bernese-workflow` instead of `scripts/`.** Not a rewrite — a single
run, compared byte-for-byte against the `scripts/` output using the tool we
already have. Until that comparison exists, the service's 198 tests are
evidence about the service, not about the science.

---

## Stage 3 — coordinates → velocities (§6)

**Status: inverted, and this is the interesting one.** The part everyone
assumed was hardest is finished and verified; the trivial plumbing around it is
untouched.

### The workflow as it stands

```
FNyyddd0.CRD  (filtered final coordinates)
   -> 00_CRD_PIVS.bat        network filter
   -> 01_GETXYZ.py           extract XYZ
   -> 02_TRANSFORM.py        frame transform
   -> 03_GETENU.py           XYZ -> ENU, relative to a reference station
   -> 04_PLOTFILES.py        per-site series files
                             (driven by RUN.py / RUNX_v*.py)
   -> PLOTS/  +  the hand-maintained `offsets` catalog
   -> vel_line_v8_newvelduetooffset_v4.m       MATLAB
   -> per-site JPGs, an `outliers` file, and Velocity_rover(regress)_10
```

### Done

**The MATLAB dependency is removed.**
`pogf_geodetic_suite.timeseries.analysis` reproduces
`vel_line_v8_newvelduetooffset_v4.m` — 161 of 165 velocity components agree to
better than 5e-6 mm/yr with `exclude_outliers=False`, verified against
PHIVOLCS' own published output. `crd_pipeline.py` covers CRD → ENU.

That closes a licensed proprietary dependency sitting in the **final step of
the scientific output**, which was a genuine succession risk.

It also surfaced things nobody was looking for — see
[`velocity_outlier_policy_delta.md`](velocity_outlier_policy_delta.md):
six sites publishing velocities fitted to *days* of data, and a catalog edit
that silently corrupted two more. **Porting a calculation is how you find out
what it was actually doing.**

### Not done

- **The 01–04 plumbing is not ported.** Reading CRDs, filtering the network,
  writing per-site files. Individually trivial; collectively the reason a human
  is still in the loop.
- **The reference-station choice is an interactive prompt**, downstream of BSW
  entirely — not a BSW panel setting. This is what makes S01R→PIMO a
  one-parameter change to a script rather than a reprocessing decision.
- **Outlier flagging is still browser-based point selection** by an analyst.
  The automatic IQR detection exists but the MATLAB never fed it to the fit,
  which is *why* the manual step exists.
- **`offsets` is hand-maintained**, unsorted, and has already caused real
  damage. See the delta document.
- **20 versions of `vel_line*.m` are snapshotted.** Only `v8_..._v4` is in
  production. That sprawl is the argument for version control, made by the
  filesystem.

### Should we go further?

**Yes — this is the best remaining value per unit of effort in the project.**

The 01–04 port is small, has no external binary dependency, has no Windows
dependency, and the hardest piece downstream of it is already verified against
production. Nothing blocks it.

Two things to decide before starting, both raised by the delta analysis:

1. **Suppress velocities whose final segment is under ~1 year.** Six Luzon
   sites currently publish rates fitted to days of scatter; TARL's published
   East velocity is 2008 mm/yr. This should be a pipeline rule, not analyst
   discretion.
2. **Sort and validate the `offsets` catalog on read.** Out-of-order records
   silently corrupt the MATLAB's fits. Our implementation sorts and is immune,
   but anyone still running the MATLAB is exposed today.

**Whether to evaluate FODITS is a genuine open question, not a foregone one.**
It would handle seasonal terms, discontinuity detection and outliers natively,
inside BSW, removing a hand-maintained catalog. Against that: our port is
verified against production output and FODITS' results would not be, so
adopting it means re-establishing trust from zero on numbers that feed public
hazard products. Recommendation: evaluate it *alongside* the ported pipeline on
the same data, and treat disagreement as information about both.

---

## How to keep this honest

Three rules, each earned by getting it wrong:

1. **Status is "does production use it?", not module count or test count.**
   `bernese-workflow` had 198 passing tests while listed at ~10%.
2. **A stage is not done until an unattended run of it has happened.** Stage 2
   earned its status with 30/30 days, not with a passing suite.
3. **Update this document when a stage moves, in the same PR that moves it.**
   The failure mode here is not disagreement, it is silence — the docs that
   went stale did so because nobody was wrong, just busy.
