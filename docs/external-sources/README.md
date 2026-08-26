# External sources — what we took, and from where

**Every idea in this repository that came from outside it should be traceable
to a source here** — for the same reason the `offsets` catalog is in git: a
claim whose origin is lost becomes folklore, and folklore cannot be checked
when it turns out to be wrong.

**This file also carries the licence basis for anything redistributed here.**
An earlier version opened by saying it was "not for licence compliance" and
then leaned on an unexamined licence assumption to decide what to commit. Both
could not hold; the licence terms are now stated per source.

### GSI content — Public Data License 1.0

出典：国土地理院ウェブサイト（<https://www.gsi.go.jp/>）
*Source: Geospatial Information Authority of Japan website.*

**Modification notice:** the `*_extracted.txt` files here are `pdftotext`
output of GSI PDFs. That conversion is **lossy** — figures, tables and page
layout are absent, and line breaks follow the PDF's columns rather than the
sentences. They are processed derivatives, **not** GSI's published documents,
and should not be presented as such. Each carries a sha256 so a reader can tell
whether they hold what was actually read.

Two of the entries below were **already found to be wrong or incomplete** once
the primary source was read. That is the argument for this file.

---

## GSI / GEONET publications

### [NAK09] — the one we extracted most from

中川弘之・豊福隆史・小谷京湖・宮原伐折羅・岩下知真子・川元智司・畑中雄樹・
宗包浩志・石本正芳・湯通堂亨・石倉信広・菅原安宏 (2009),
「GPS 連続観測システム（GEONET）の新しい解析戦略（第４版）による
ルーチン解析システムの構築について」,
*国土地理院時報* (Journal of the Geospatial Information Authority of Japan)
**118**, 2009.

Nakagawa, H., Toyofuku, T., Kotani, K., Miyahara, B., Iwashita, C., Kawamoto,
S., Hatanaka, Y., Munekane, H., Ishimoto, M., Yutsudo, T., Ishikura, N.,
Sugawara, Y. — "Development and Validation of GEONET New Analysis Strategy
(Version 4)".

- **URL:** <https://www.gsi.go.jp/common/000054716.pdf>
- **Retrieved:** 2026-08-25
- **Language:** Japanese
- **Local copy:** `nakagawa2009_gsi118_extracted.txt` — `pdftotext` output,
  37194 bytes,
  sha256 `4f62c0135922a7fa…`. The PDF itself is **not** committed; it is GSI's to
  distribute. The extracted text is kept because a fetch that worked once is
  not a source that will work in five years.

**What we took, and where it went:**

| idea | used in |
|---|---|
| Partition by **station age first**, not geography — 基本網 (~950 pre-2001) vs 追加網, each then split into 5 regional clusters | `geo006_network_architecture.md` §1 |
| Backbone is **drawn from** the basic network's regional clusters, not separately installed | §1 |
| GSI's stated reason: long-history stations minimise changes in network *shape* | §1 |
| **V3's defect** — pairwise backbone↔regional combination gave non-unique troposphere at backbone stations | §2 |
| **V4's fix** — strict top-down hierarchy, each layer fixed before the next | §2 |
| The change was **gated on Bernese 5.0** carrying troposphere in normal-equation files | §2 |
| GSI **bounded rather than fixed** a 4 ppb solid-earth-tide scale bug, and said why | §3 |
| V4 validated by **reprocessing the same data both ways** | §3 |
| **2008 Iwate**: V3's coherent ~2 cm northward field was a stationary-front artefact | §3 |
| ~1,020 km 八郷–猿払 baseline: V4 reduced annual signal and scatter | §3 |

**What we did NOT take:** anything about GSI's semi-dynamic datum, their
ionosphere handling, or F5. Those are elsewhere or still open.

### [KOT09] — the companion paper on the fixed point

小谷京湖・吉田賢司ほか (2009),「GPS 連続観測システム（GEONET）解析固定点座標算出
手法について」, *国土地理院時報* **118**.

- **URL:** <https://www.gsi.go.jp/common/000054718.pdf>
- **Retrieved:** 2026-08-25 · **Language:** Japanese
- **Local copy:** `kotani2009_gsi118_fixedpoint_extracted.txt`, sha256 `ab39f77b784d78c5…`

| idea | used in |
|---|---|
| GEONET V4 constrains the whole network through **one station, Tsukuba-1 (92110)** | `geo006_network_architecture.md` §4b |
| Under V3 its coordinates came from a piecewise-linear model that missed the vertical annual variation, producing **an apparent annual vertical signal at every GEONET station** | §4b |
| V4 determines that station daily inside a **wide-area IGS solution** instead | §4b |

Taken because it supplies the *mechanism* behind a conclusion the research
brief had already reached on other grounds — that POGF's multi-station minimum
constraint is more robust than a single fixed station.

### [MIY09] — retrieved by citation, and NOT used

宮原伐折羅・野神憩・梅沢武・岩下知真子・川元智司 (2009),「GPS 連続観測システム
（GEONET）の解析戦略（第４版）から見た地殻変動について」, *国土地理院時報* **118**,
31-36. <https://www.gsi.go.jp/common/000054720.pdf>

Recorded because **an earlier draft predicted the cluster-sizing rule would be
here, and that was wrong.** The title — "crustal deformation *as seen from*
strategy V4" — is deformation results, not architecture. The prediction came
from the author list rather than the title.

Kept as a negative result: it stops the next reader repeating the guess.

---

## Open lead — where the cluster-sizing rule is

**Not retrieved. Recorded so the next attempt starts from a target rather than
a search.**

測地観測センター (2004),「小特集 電子基準点 1,200 点の全国整備について」,
*国土地理院時報* **103**, 1-51.
Front matter: <https://www.gsi.go.jp/common/000024797.pdf> — retrieved
2026-08-25, extracted as `gsi103_2004_frontmatter_extracted.txt`,
sha256 `42475917730c7ef3…`

That PDF is **table of contents and summary only** (~31 KB of text for a
51-page issue); the body sections are separate files. But the TOC pins the
target exactly:

```
１．３  電子基準点の定常解析（畑中 雄樹）
  １．３．１  GEONETの定常解析戦略の変遷     ← the cluster design should be here
  １．３．２  解析戦略の変更点
  １．３．３  解析結果の精度
  １．３．４  定常解析のさらなる改良に向けて
```

Hatanaka §1.3.1 — *"evolution of the GEONET routine analysis strategy"*. Same
Hatanaka who co-authored [NAK09], and [NAK09] says the network structure was
inherited unchanged from V3, so a 2004 description should still describe the
V4-era architecture.

**How to retrieve a GSI PDF from this machine** — the method matters as much as
the target:

1. `curl` **cannot reach `gsi.go.jp` at all**. The server requires legacy TLS
   renegotiation that OpenSSL 3 refuses
   (`error:0A000152 unsafe legacy renegotiation disabled`). This is not a
   proxy or firewall problem and no curl flag tried worked.
2. **WebFetch downloads it** and saves the binary locally even when it cannot
   parse it. Then `pdftotext <file> out.txt` extracts the Japanese cleanly.
3. Volume index pages **302-redirect to the GSI homepage**, so the issue cannot
   be walked. Article URLs must come from a web search instead.
4. **The IDs are sequential in one global namespace**: `000024797` is vol 103
   (2004), `000054716`–`000054720` are the five vol 118 (2009) papers. The vol
   103 body sections are probably near `000024797` and could be probed.

**Why this was left open.** It is a number — stations per cluster — that only
matters if the PH network grows several-fold. At 76 stations a single cluster
is probably correct (`geo006_network_architecture.md` §4). What *was* recovered
from [NAK09] is the load-bearing part: the age-based partition, the V3→V4
combination mechanics, and the single-fixed-point failure mode.

---

### Already cited in `geonet_bernese_strategy_research.md`

That document carries its own source table with tags **[FIG13] [TSU17] [TAK23]
[TOB15] [OHK15]**, plus **[REPO]** (verified against this repo) and **[MEM]**
(prior session notes, flagged as second-hand). **It is the authority for those
five**; this file does not duplicate it.

Two corrections found by reading primaries, recorded because they are the
reason this register exists:

- **[TAK23]** was first cited from a secondary source as showing VMF1 drove
  F5's improvement. The abstract says the gain was **entirely from shortened
  troposphere intervals**, not VMF1. An earlier draft recommended a change on
  the strength of the wrong reading.
- **[NAK09]** was recorded as *"in Japanese and not reachable"*. It was
  reachable; it needed `pdftotext` rather than a fetch. **"Not reachable"
  meant "I did not try hard enough"**, and it closed a question the brief
  itself called load-bearing.

---

## Philippine sources

**[OHK15]** Ohkura, T., Tabei, T., Kimata, F., Bacolcol, T.C., et al., "Plate
Convergence and Block Motions in Mindanao Island…", *Journal of Disaster
Research* **10**(1), 2015.

| idea | used in |
|---|---|
| Hierarchical processing of PHIVOLCS campaign data: PIMO tightly constrained → **NMMB chosen as Mindanao reference because it had the longest observation period** → further pairs chained by observation overlap | `bernese_workflow_geonet_actions.md` §0; `geo006_network_architecture.md` §4 |

Worth naming: that selection rule — **longest observation period** — is the
same principle GSI arrived at with 基本網, reached independently on our own
data. Convergent evidence, not a borrowed idea.

**[TOB15]** carries PHIVOLCS co-authors (Luis, **Pelicano**, Bacolcol). Its
3-hourly troposphere interval on Philippine data is what showed POGF's hourly
final solve is already **shorter** than the regional precedent — which is why
the recommendation to shorten it was withdrawn.

---

## Stanford CDFM — `dc3dm` (Okada DC3D source)

**Recorded, NOT vendored.** Licence terms below are the reason.

Bradley, A.M., *dc3dm: Software to form and apply a 3D DDM operator for a
nonuniformly discretized rectangular fault*, v0.3, CDFM Group, Geophysics,
Stanford. <https://pangea.stanford.edu/research/CDFM/software>
Retrieved 2026-08-26; extracted locally to `temp/dc3dm_v0.3/`.

**Licence: Eclipse Public License 1.0** — weak copyleft. This repository is
MIT. EPL code may sit inside a differently-licensed larger work, but the EPL
files stay EPL and must be identified as such. That is a deliberate decision,
not a free action, so nothing is committed here yet.

**Why it is worth recording anyway:** `external/dc3omp.f` is Okada's `DC3D`
**with a numerical-accuracy fix by A.M. Bradley (Nov 2012)**. Stock DC3D
suffers cancellation error in `R + xi` whenever `sqrt(eta^2+q^2)/R` is small,
producing error in **four cones extending from the rectangle's corners** — not
merely at exact singularities. If `DC3D` is ever needed, take **this** version
rather than the NIED original.

| what it would be for | status |
|---|---|
| source for `disloc3d`, used by `06 Ku-en` and absent from this tree | the gap `disloc.py` explicitly left open |
| `dc3dm` itself — hierarchical-matrix DDM on nonuniform meshes for rate-and-state earthquake-cycle simulation | **out of scope**; MOVE Faults does interseismic dislocation inversion |

**Checked and came back negative:** the `disloc.c` vendored into
`modeling/_disloc/` has the same unguarded pattern — `rrx = 1/(r*(r + xi))`,
while `r + et` *is* guarded — but probing the singular ray from 1e-1 down to
exactly 0 gives smooth convergence with no blow-up or discontinuity. No
evidence it suffers the pathology; Okada 1985 (surface) and 1992 (internal) are
different formulations. Recorded so the lead is not chased twice.

---

## Bernese GNSS Software

- **DOCU52.pdf** — Bernese 5.2 documentation, AIUB. Local at `~/bernese-docs/`.
  §22.9 (multi-session parallelism, `SUPERBPE`/`REPR_MODE`) and Eqn 9.10
  (normal-equation stacking is matrix addition, hence order-independent).
- **TERMINAL.pdf** — Bernese 5.4 tutorial, AIUB.
- **<https://www.bernese.unibe.ch/faq/>** — retrieved 2026-08-25 for the
  `HELMTR: TOO MANY PARAMETERS` entry, which confirmed DOY 036's HELMR1
  failure was correct outlier rejection rather than a defect.

Neither manual is committed; both are AIUB's to distribute.

---

## Rules

1. **Cite the primary.** Both corrections above came from trusting a secondary.
2. **Record the date retrieved.** A URL is not a citation; a URL plus a date is.
3. **Say what was taken.** "We read X" is not attribution — the table says which
   *idea* moved, and into which file.
4. **Check the licence, then decide what to keep.** GSI website content is
   **Public Data License 1.0**, which permits redistribution with attribution
   and a note that the content was processed. That is why the extracted text
   below is committed. AIUB and commercial-publisher PDFs carry no such grant
   and are **not** committed.

   **Extracting text does not change a source's licence — the text is the
   work.** An earlier version of this rule said "keep extracted text, not the
   source… publishers' PDFs stay theirs", reasoning from *format*. That is
   wrong: `pdftotext` output of a paper is the paper, title page through
   references. It happened to land on the right answer for GSI because PDL 1.0
   permits redistribution anyway; applied to the AIUB manuals listed below it
   would have produced infringement while sounding equally principled.
   Caught in review of PR #141.
5. **"Not reachable" needs a method attached.** Say what was tried.
