# External sources — what we took, and from where

**Every idea in this repository that came from outside it should be traceable
to a source here.** Not for licence compliance — for the same reason the
`offsets` catalog is in git: a claim whose origin is lost becomes folklore, and
folklore cannot be checked when it turns out to be wrong.

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
4. **Keep extracted text, not the source.** A fetch that worked once is not a
   source that will work later. Publishers' PDFs stay theirs.
5. **"Not reachable" needs a method attached.** Say what was tried.
