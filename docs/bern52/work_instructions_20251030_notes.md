# Notes on `Work_Instruction_ao20251030.docx`

**Source:** PHIVOLCS MOVE Faults *Work Instruction for Processing GPS Data*,
October 2025 revision, placed in this repo 2026-08-11.
**Authors:** Cassandra Joy V. Cabigan, Alyssa Dane S. Pariñas, Abegail Riva L.
Abrenica, Kurt Zedrick M. Baldemoro, Ken Louis L. Villar, Alfie R. Pelicano.
Project leader: Teresito C. Bacolcol, PhD, CESO IV.

**This is the authoritative SOP for how PHIVOLCS actually processes GPS data
with BSW 5.2.** It is the source document behind
`docs/work_instructions_review.md` (which reviewed the slightly earlier
`ao20251017` revision).

## Extracting it

A `.docx` is a ZIP archive, so both text and figures come out without special
tooling — and the figures matter here as much as in the BSW manual, since most
of the document is annotated UI screenshots.

```bash
unzip -q Work_Instruction_ao20251030.docx -d /tmp/wi
ls /tmp/wi/word/media/            # 113 images, ~12 MB
# text WITH image anchors in document order:
#   parse word/document.xml, emit <w:t> runs per <w:p>,
#   and note r:embed="rIdNN" occurrences inline
# map rIdNN -> media filename via word/_rels/document.xml.rels
```

Text alone loses the ordering relationship between an instruction and the
screenshot illustrating it, which is most of the document's value. Emitting
`[[IMAGE rIdNN]]` markers inline preserves it.

## Finding 1 — the review's S01R recommendation was not adopted

`docs/work_instructions_review.md` §"Issue 2" recommended expanding §6.2.4.2
to explain *why* S01R, and to state the alternatives (PIMO, IGS network
average, another PHIVOLCS site).

**The `ao20251030` text is verbatim identical to the `ao20251017` text the
review quoted.** The recommendation was not taken up in this revision. The
sentence granting permission to change reference station is present — *"the
choice of reference station for velocity computations is not fixed, as other
stations may be used based on needs or the intended analysis"* — but the
"Why S01R?" rationale and the named alternatives are not.

Relevant to the standing S01R-vs-PIMO question (runbook §4b.9): the SOP
permits the switch and gives no argument for or against it.

## Finding 2 — the `offsets` file is PHIVOLCS's own discontinuity catalog

§6.2.6 and its screenshot reveal a maintained event catalog that nothing in
this repo had recorded. Format is one record per line:

```
SITE  decimal_year  TYPE

ALBU  2017.5147  EQ      EQ = earthquake
BLNA  2019.5257  CE      CE = change of equipment
CACA  2020.0356  VE      VE = volcanic eruption
BAYB  2014.7830  UK      UK = unknown cause
```

Decoding validated against a known event: `CACA 2020.0356 VE` → day 13.0 of
2020 → **13 January 2020**, matching the Taal Volcano eruption of 12 January
2020. The decimal-year convention and the `VE` tag both check out.

The SOP states it plainly: *"This file must be updated whenever new offsets
are identified."*

**Why this matters for the FODITS question (plan doc, Tier 4):** FODITS
consumes predefined discontinuities from a station-information file (`STA`),
an earthquake list (`ERQ`), and a user event list (`EVL`). **PHIVOLCS already
maintains, by hand, exactly the metadata FODITS wants** — years of curated
site/epoch/cause records, including the equipment changes and volcanic events
a USGS earthquake catalog would never contain. Migrating to FODITS would be a
format conversion of an existing asset, not a cold start. That materially
improves the case for evaluating FODITS, and the `offsets` file should be
treated as a **first-class project asset** — it is irreplaceable institutional
knowledge, and this repo does not currently hold a copy.

## Finding 3 — the current time-series workflow, and a succession risk

Reconstructed from §6.2:

```
FNyyddd0.CRD  (filtered final coordinates)
   -> plot_v2.py        prompts for reference station (S01R), converts
                        daily XYZ -> ENU, writes an ENU file plus one
                        file per site
   -> PLOTS/            plus the hand-maintained `offsets` file
   -> vel_line_v8.m     MATLAB
   -> per-site JPG time series, an `outliers` file, and
      Velocity_rover(regress)_10 (E/N/U velocities per site)
```

**The velocity computation depends on MATLAB** — proprietary and licensed.
Combined with the project's stated succession concern (see the repo's audit
notes: the code of record on a personal account, no fixity on the archive),
a licensed dependency in the final step of the scientific output is worth
flagging. FODITS would remove it, since velocity estimation and discontinuity
handling are exactly what it does; that is a second, independent argument for
the Tier 4 evaluation.

Note also that the reference-station choice is a **prompt in `plot_v2.py`**,
downstream of BSW entirely — not a BSW panel setting. This confirms the
earlier inference (runbook §4b.9) that switching S01R→PIMO is a parameter
change to a downstream script, not a reprocessing-pipeline change.

## Finding 4 — a likely source of the "§5.2" confusion

The work instruction's own numbering is:

- **§5.1 Installation** (p. 25)
- **§5.2 Campaign setup** (p. 26)

So "section 5.2" is unambiguous *within this document* and means campaign
setup. The BSW-installation-verification sections are in DOCU52 —
**§23.3** (verification via the BPE examples) and **§25.2** (the UNIX/Linux
install guide). Worth keeping the document name attached to any section
number in future notes.

## Not yet read

Most of the document. Sections likely to repay attention:

- **§4 Data conversion** (Trimble/Leica raw → RINEX, antenna height
  computation, and the Python automation in §4.3–4.4) — directly relevant to
  the ingestion pipeline, and the only place the antenna-height convention is
  written down.
- **§5.1 Installation** — how PHIVOLCS installs BSW 5.2, for comparison with
  the R740's 5.4 install.
- **§5.6.4 Adding an IGS reference site** and **§5.6.5 Updating GEN folder** —
  bears on the AIRA chronic-offset finding (runbook §4b.12) and on how
  reference-frame files are refreshed.
- **§6.3 Outlier removal** — the manual counterpart to what
  `scripts/coord_repeatability.py` and FODITS do.
