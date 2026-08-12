# MOVE Faults workflow: full inventory and automation status

**Source:** full ingestion of `Work_Instruction_ao20251030.docx` (737 text
blocks + 113 embedded images), 2026-08-12. Companion to
`work_instructions_20251030_notes.md`.

**Purpose:** establish exactly what the PHIVOLCS GPS workflow consists of, so
the R740 automation target is measured against the real thing rather than
against the part we happen to have automated already.

**Headline:** the SOP is a **Windows, GUI-and-prompt-driven, three-stage
pipeline**. The gps3 work to date has automated most of **stage 2**
(BSW processing) and none of **stage 1** (conversion) or **stage 3** (time
series / velocities). Stage 3 additionally carries a **MATLAB dependency**.

---

## The three stages

```
STAGE 1  RAW -> RINEX                     §4     Windows .exe + Python prompts
   Trimble .T00/.T01/.T02 --runpkr00--> .DAT/.TGD --teqc--> SITEJJJ0.YYo
   Leica .m00/.m01/...    ----------------teqc--> SITEJJJ0.YYo
   antenna height from paper log sheets -> Excel -> -O.pe parameter

STAGE 2  RINEX -> daily coordinates       §5     BSW 5.2 GUI + BPE
   campaign setup, 8 STA-folder files, PHIVOL_REL.PCF, BPE run
   -> F1_YYDDD0.CRD (the target output) + NQ0/SNX/TRO/TRP/PRC

STAGE 3  coordinates -> time series       §6     Python prompts + MATLAB
   F1_*.CRD --filter-fncrd.bat--> FN*.CRD --plot_v2.py--> PLOTS/
   + offsets --vel_line_v8.m (MATLAB)--> JPG plots, outliers,
                                          Velocity_rover(regress)_10
   --outlier_input-site.py--> manual outlier removal -> rerun MATLAB
```

---

## Inventory A — third-party programs

| Program | Source | Stage | Role | Linux? |
|---|---|---|---|---|
| `runpkr00.exe` | UNAVCO | 1 | Trimble raw → `.DAT`/`.TGD` | Linux build exists |
| `teqc.exe` | UNAVCO | 1 | raw → RINEX 2, header edit, decimation, splicing | Linux build exists; **UNAVCO retired teqc** |
| `fixdatweek.exe` | Trimble | 1 | repairs GPS-week rollover (Trimble 5700) | Windows-only, likely |
| Microsoft Excel | — | 1 | `compute_ant-h.xlsx` antenna-height sheet | replaceable |
| Notepad++ | notepad-plus-plus.org | 1,2 | editing `.bat`, STA, BLQ files | n/a on Linux |
| Total Commander / Explorer | — | all | file management | n/a |
| **BSW 5.2** | AIUB | 2 | the processing engine | **5.4 installed on R740** |
| Perl ≥ 5.24 | ActiveState | 2 | BPE scripting | present (5.38.2) |
| `gzip` | gzip.org | 2 | RINEX (de)compression, must be on `PATH` | present |
| Hatanaka `CRX2RNX` | terras.gsi.go.jp | 2 | CRINEX → RINEX | **present** — BSW ships it at `$X/SCRIPT/EXE/CRX2RNX` (uppercase), already on `PATH` via `LOADGPS.setvar` |
| `Net::FTPSSL` 0.40 | CPAN/ppm | 2 | `FTP_DWLD` over FTPS | **not needed** — we bypass FTP_DWLD |
| **MATLAB** | MathWorks | 3 | `vel_line_v8.m` — velocities + plots | **licensed; no R740 install** |
| Python | python.org | 1,3 | the project scripts | present |
| FileZilla | — | 2 | manual GEN-folder update, IGS downloads | replaceable by script |

## Inventory B — project scripts (Google Drive: `03 GPS > GPS Processing > 03 Scripts`)

**None of these are in this repo.** They live only on Google Drive and staff
machines. That is a succession risk in its own right.

### `01 RINEX conversion`
| File | Role |
|---|---|
| `campaign_v5.py` | interactive campaign-data conversion (prompts: site, `.DAT` name, antenna type 1/2/3, antenna height) |
| `continuous_v5.py` | interactive CORS conversion (prompts: operator name, site, 1=runpkr00 / 2=Trimble→RINEX / 3=Leica→RINEX) |
| `compute_ant-h.xlsx` | slant → vertical antenna height |

### `02 Time Series`
| File | Role |
|---|---|
| `filter-fncrd.bat` | `F1_YYDDD0.CRD` → `FNYYDDD0.CRD`, filtered to local + IGS sites; moves originals to `F1CRD/` |
| `plot_v2.py` | prompts for reference station (S01R); XYZ → ENU; writes per-site PLOT files and `123` index |
| `vel_line_v8.m` | **MATLAB**; time-series JPGs, `outliers`, `Velocity_rover(regress)_10` (E/N/U, split at offsets) |
| `outlier_input-site.py` | interactive: right-click outliers on a plot → `OUTLIERS.txt` |
| `offsets` | **the event catalog** — `SITE decimal_year TYPE`, TYPE ∈ {EQ, VE, CE, UK} |

### Batch files generated *by hand* during the workflow
`convert2dattgd.bat`, `dattgd2rinex.bat`, `leiconvert2rinex.bat`,
`fixdatweek.bat` — each built by `dir/b > x.bat`, then hand-edited in
Notepad++ to delete non-data lines and prepend the command. **This is the most
mechanical, most error-prone step in the SOP and the easiest to eliminate.**

## Inventory C — BSW programs driven through the GUI (stage 2)

`RNX2STA` (STA), `RXOBV3` (CRD+ABB), `GRDS1S2` (ATL), `EDITPLD` (PLD),
`NUVELO` (VEL, NUVEL1A model), `EDITCLU` (CLU), `STAMERGE` (merge IGS.STA),
`RNXGRA` (data screening thresholds), plus the BPE itself running
`PHIVOL_REL.PCF`.

The eight per-campaign STA-folder files: **STA, CRD, ABB, ATL, PLD, VEL, CLU,
BLQ** — created once, then maintained by hand forever after.

## Inventory D — external data sources

| Source | Endpoint | Products |
|---|---|---|
| CDDIS | `ftps://gdc.cddis.eosdis.nasa.gov` (anonymous; email as password) | IGS final GPS/GLONASS orbits `igswwwwd.sp3.Z` / `iglwwwwd.sp3.Z`, weekly ERP `igrwwww7.erp.Z`, daily IGS RINEX `pub/gps/data/daily/YYYY/JJJ/25d` |
| AIUB | `ftp.aiub.unibe.ch` | CODE DCB `P1C1yymm.dcb.Z`/`P1P2yymm.dcb.Z`, CODE ION `CODwwwwd.ion.Z`, `IGS14_R.CRD`/`.VEL`/`IGS.STA`, `GEN/` contents, `C04_YYYY.ERP` |
| Chalmers/Onsala | `holt.oso.chalmers.se/loading/` | ocean-tide loading (BLQ), **FES2004**, delivered by **email** |
| Google Drive | project folder | the scripts above, plus a "BERN52 Solutions and Updates" guide |

**Note for the R740:** `ftp.aiub.unibe.ch` is **firewalled from gps3** (runbook
§1.1c / `fetch_igs_products.sh`). The CODE products are reachable instead via
the SWITCH S3 mirror `https://zhw-b.s3.cloud.switch.ch/aiub/`. Any automation
of §5.6.5 (GEN update) or §5.7.1.2 must use that path, not the SOP's FTP host.

## Inventory E — IGS reference sites: the SOP list differs from LUZON's

SOP §5.7.2.3 names **twelve**: AIRA, ALIC, **BTNG**, **CUSV**, DAEJ, DARW,
**GUUG**, MCIL, **NTUS**, PIMO, PNGM, **TNML**.

The LUZON campaign we reprocessed staged **nine**: AIRA, ALIC, **BASC**,
**CLAV**, DAEJ, DARW, MCIL, PIMO, PNGM.

Five in the SOP (BTNG, CUSV, GUUG, NTUS, TNML) were **not** in the LUZON set;
two in LUZON (BASC, CLAV — both PHL) are not in the SOP list. Not necessarily
wrong — LUZON is a regional subset and the SOP describes the national
PHIVOLCS campaign — but it means **"the fiducial set" is not one fixed thing**,
and any national-scale automation must take the station list as configuration
rather than hardcode either list. Relevant to the subnetwork plan.

---

## Automation status against the R740

### Stage 2 — largely done
| SOP step | R740 replacement | State |
|---|---|---|
| §5.5.1 `FTP_DWLD` | `scripts/fetch_igs_products.sh` | **done** (CODE via SWITCH S3; AIUB FTP firewalled) |
| §5.3.10 BLQ web form + paste | `scripts/merge_blq.py` | **done** (still needs the manual Onsala email round-trip) |
| §5.2–5.3 GUI campaign setup | `scripts/stage_luzon_campaign.sh` | **done for LUZON**, not generalised |
| §5.4 PCF editing in `EDITPCF` | `scripts/derive_luzon_pcf.py` | **done** (BSW 5.4 format) |
| §5.6.1 daily BPE via GUI | `scripts/run_luzon_month.sh` | **done** (idempotent, resumable) |
| §5.5.5 check `.PRC` output | `run_luzon_month.sh` freshness check | **done** |
| — | `coord_repeatability.py`, `network_coherence_scan.py` | **new QC, not in the SOP at all** |

### Stage 1 — not started
Everything in §4. Specific blockers:
1. **`teqc` is retired and already demonstrably insufficient — this is
   settled, not a new proposal.** See
   `docs/project_documentation/gfzrnx_vs_teqc_rinex3_evidence.md` (2026-07-01):
   teqc `2019Feb25` **hard-refuses RINEX 3.04 on line 1** ("must be RINEX
   Version <= 2.11"), on data PHIVOLCS already ingests (CUSV 2026/087,
   multi-GNSS incl. BeiDou-3); `gfzrnx` 2.2.0 reads the same 48 MB file in
   ~14 s and QCs GPS+GLONASS+Galileo+QZSS+BeiDou. The migration trigger is
   **met**, not pending.
   Two caveats for *this* stage: (a) `gfzrnx` is **not currently installed on
   gps3** — it is referenced by `pogf-geodetic-suite`'s QC and by that
   evidence doc, but `command -v gfzrnx` finds nothing here; (b) gfzrnx
   handles **RINEX manipulation**, not **Trimble/Leica proprietary decoding**,
   so it replaces teqc's RINEX role but not `runpkr00`'s.
2. **`runpkr00` (Trimble) and Leica MDB reading** have no obvious open
   replacement. Trimble's own `convertToRINEX`, or `runpkr00`'s Linux build,
   are the realistic options. **This needs a decision before stage 1 can be
   automated at all.**
3. **Antenna heights come from paper log sheets.** No amount of scripting
   removes the transcription step; the most that can be automated is
   validation (range checks, the slant-vs-vertical and cm-vs-m traps the SOP
   itself warns about, which cause 5–15 cm and 100× errors respectively).
4. `fixdatweek` (GPS-week rollover, Trimble 5700) is Windows-only.

### Stage 3 — not started, and the MATLAB dependency is the crux
1. `filter-fncrd.bat` — trivial to reimplement.
2. `plot_v2.py` — XYZ→ENU with a reference station; ~straightforward, and we
   already have the transform in `coord_repeatability.py` and
   `network_coherence_scan.py`.
3. **`vel_line_v8.m` is MATLAB** and produces the project's actual scientific
   deliverable (site velocities, split at offsets). **Neither MATLAB nor
   Octave is installed on gps3** (verified 2026-08-12). Options: (a) port to
   Python/NumPy, (b) **evaluate FODITS**, which does discontinuity detection,
   velocity estimation, outlier handling and seasonal terms natively in BSW —
   see the plan doc's Tier 4.
4. `outlier_input-site.py` is deliberately interactive (visual outlier
   picking). FODITS's statistical outlier test is the automated counterpart.
5. **The `offsets` file must be brought into version control.** It is
   hand-curated institutional knowledge going back years, it exists only on
   Google Drive and staff machines, and it is precisely the input FODITS
   consumes as an event list. Losing it would be worse than losing any script
   here.

---

## Recommended order of work

1. **Copy the `offsets` file and the five Google Drive scripts into this
   repo.** Zero-risk, and it is the single largest reduction in project
   fragility available right now. Nothing else on this list matters if the
   inputs are lost.
2. **Stage 3 before stage 1.** It is closer to the science, the MATLAB
   dependency is the sharpest single-point risk, and FODITS may collapse
   items 2–5 into one configured BSW program we already have installed.
3. **Generalise stage 2 from LUZON to arbitrary campaigns** — the station list
   (Inventory E) is the parameter that must stop being hardcoded.
4. **Stage 1 last**, and start it with the format decision (item 2 above),
   not with scripting.
