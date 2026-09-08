# Is the WVFS single-frequency data usable? A scoped proposal

**The short answer is that nobody knows, and the reason is not that the
question is hard — it is that the measurement which would answer it has never
been made.** This document says exactly what to run, against what, and which
number decides it.

Written 2026-09-08 from the recovered archive on gps3. Every claim below is
from files in `/srv/gnss-archive/`, not from recollection.

---

## 1. What the archive actually contains

### The network is far larger than what was ever processed

**54 sites** in the Metro Manila / Marikina box (14.2–14.9 N, 120.8–121.4 E)
have coordinates in `docs/bern52/crd_catalog.csv`. They fall into two groups
with very different file counts:

| group | n_files | examples |
|---|---|---|
| campaign sites | **52–53 each** | LMSA, TUNA, ADMA, PRJ4, CENT, TESD, HEAL, RGMH, SMPH, CEMB, TYTY, MTDW, BAYA, TUMA, TNHS, SMTC, CMWL, MLRA, MTLB, VCAC … ~30 sites |
| continuous anchors | 600–7,000 | PIMO 7071, PTAG 3004, MARL 1355, MUNT 998, MARK 955, PIVS 949, ANTP 947, MALY 619, CNTA 619 |

The uniform 52–53 count is the signature of **one coordinated campaign** across
the network. The anchors are the dual-frequency "stable fixed points" the
network was designed around — that design is visible in the data.

### NCKU processed six of those fifty-four

`toto_D/programs from NCKU/Profile/velocity/NONE/fit-h.out` is the only
velocity output in the archive. Its sites are NCKU-internal numeric IDs, which
map onto real codes by position:

| NCKU id | site | distance | value | sigma | \|v\|/σ |
|---|---|---|---|---|---|
| 2762 | LMSA | 6 m | 5.27 | 13.73 | 0.38 |
| 3950 | TUNA | 5 m | −31.57 | 16.65 | 1.90 |
| 9865 | PIVS | 18 m | −20.96 | 12.91 | 1.62 |
| 9866 | MALY | 5 m | 31.51 | 16.30 | 1.93 |
| 9875 | **SOLD** (NCR) | 12 m | −5.62 | 35.62 | 0.16 |
| 9906 | RGMH | 4234 m | −5.72 | 17.16 | 0.33 |
| PIMO | PIMO | 4 m | 0.10 | 0.02 | fixed reference |

**Not one site reaches 2σ.** Three are below 0.4σ — indistinguishable from
zero. The two largest, MALY (+31.5) and TUNA (−31.6), sit at ~1.9σ and point in
opposite directions.

So "the vectors have no trend" is the correct reading. There is no trend to see
because the velocities are not resolved. Any map of them is a map of the noise.

### The Bernese single-frequency campaign is Taiwanese data

`PHIVOLCS_single/wvfs/` looks like the missing piece and is not. Its five
sites — ASJH, ESEQ, HHAR, HHHS, NMTH — are at **22°59′–23°03′ N,
120°13′–120°20′ E**: Tainan, where NCKU is. Site spacing ~10 km. Observations
are 2017 DOY 273–279, `TYPES OF OBSERVATIONS: C1 L1 D1`, processed with a
**global ionosphere model from CORS**.

It is a **worked training example on data NCKU controlled**, named for what it
was teaching rather than what it contains.

### Nothing applies the method to the Philippine network

The Taiwan campaign runs `CODSPP → SNGDIF → MAUPRP → GPSEST → QIF` and stops.
There is **no ADDNEQ2, no coordinate comparison, no repeatability output** —
and no equivalent campaign on NCR sites anywhere in the archive.

**That is why the question was never answerable.** The method was demonstrated;
it was never run on your data, and the one step that would report precision was
never reached even on theirs.

---

## 2. Why this is worth doing rather than abandoning

Single-frequency L1 cannot form the ionosphere-free combination, which is the
real limitation. But the limitation is a function of **baseline length**, not of
single-frequency per se:

* On baselines under ~20 km the ionospheric delay largely cancels between
  stations, and L1 with a global ionosphere model reaches **3–5 mm** horizontal
  repeatability on 24-hour sessions.
* NCKU referenced to **PIMO**, which is 30–50 km from most of the network.
  That is where the ionosphere stops cancelling and starts dominating —
  consistent with the 13–36 sigmas observed.
* The network has **its own anchors**: PIVS, MARK, ANTP, MALY, PTAG are 5–15 km
  from most campaign sites.

Over 2009–present, even with gap years, 3–5 mm repeatability yields velocity
precision around **0.5–1 mm/yr** — enough to resolve WVFS creep of a few mm/yr.
At 30 mm it resolves nothing, ever, however many years are added.

**Which of those is true has never been measured.** That is the entire
uncertainty.

---

## 3. The proposal

### Data

One WVFS campaign — the 52–53 epoch cluster — using its **own anchors** as
reference rather than PIMO:

```
reference   PIVS, MARK, ANTP, PTAG   (dual-frequency, 5-15 km baselines)
estimated   the ~30 campaign sites at 52-53 epochs each
```

### Method

Bernese 5.4 (working on gps3, BRN-001 verified), single-frequency L1 with a
global ionosphere model — the same configuration `PHIVOLCS_single/wvfs`
demonstrates, applied to NCR data.

### The step that has never been run

Extend past `GPSEST` to `ADDNEQ2`, and compute **daily coordinate repeatability**:
the scatter of each site's daily position about its own mean, in north, east
and up.

### The number that decides it

| daily repeatability | verdict |
|---|---|
| **σ ≈ 3–5 mm** horizontal | usable. The archive can produce WVFS velocities, and the NCKU result was a processing choice — the PIMO baseline — rather than a limit. Proceed to a full multi-year solution. |
| **σ ≈ 10–20 mm** | marginal. Velocities possible only over the full 2009–present span, and only for the largest signals. Worth stating the detection threshold explicitly. |
| **σ ≈ 30 mm** | not usable at these baselines. A network-design finding: single-frequency at this geometry cannot resolve WVFS creep, and no amount of reprocessing changes it. |

**Every outcome is a result**, and the third is as valuable as the first —
it ends a decade of uncertainty and redirects effort to instrumentation rather
than processing.

---

## 4. A precondition: shared site codes

Some codes name more than one physical monument, and this is not hypothetical
for WVFS. Two confirmed:

```
SOLD   [154, 53]   11.03386 N 125.74071 E (Leyte)   and   14.40085 N 121.03742 E (NCR)
                   632 km apart, disjoint provenance
CENT   [ 53,  53]  two monuments, both campaign-sized
```

The NCR SOLD is **Soldiers Hills Village, Putatan, Muntinlupa** — confirmed
independently of the coordinates, by institutional memory. It sits 1.5 km from
`MUNT`, which is also in Muntinlupa, so the two are neighbours in the same
municipality and the code collision is with a site 632 km away in Leyte rather
than with anything local.

Worth recording because the place name is stronger evidence than a coordinate
match: it identifies the monument, not merely a position. Nothing else in the
archive carries it — the site name appears in no header, no station-information
file, and no README.

The NCR SOLD is NCKU's site `9875`. If its 53 files were ever processed
alongside Leyte's 154, that solution is contaminated.

`build_crd_catalog.py` already detects this — 118 sites carry `ambiguous=yes`.
But **most of those 118 are not real collisions**: the discriminator is the
size of the second cluster.

```
genuine     SOLD [154, 53]      CENT [53, 53]
noise       POTR [368, 2]   MARK [704, 4, 4, 2 ...]   PIMO [6745, 25, 2 ...]
```

A second cluster of ≥10 files is a real monument; ≤4 is a diverged solution
that the 1 km clustering radius turned into its own group. **`cluster_extent_m`
is not a reliable indicator on its own** — POTR reports 10,290 km, which is a
garbage coordinate rather than two sites.

**Action before processing:** run the cluster-size test across all 118, list the
genuine collisions, and confirm none of them is mixed within a single campaign.
Cheap, and it protects everything downstream.

---

## 5. What this does not cover

* **Velocities.** 52–53 epochs in one campaign give *coordinates*. A velocity
  needs the repeated occupations across 2009–present. This proposal measures
  whether those coordinates are precise enough to be worth combining — it does
  not produce the velocity field.
* **The 2009–present holdings.** This document inventories what reached gps3.
  Campaign years not represented here are a separate question.
* **MOQC and MESA.** Named from institutional memory; **neither appears
  anywhere in the archive**, under any extension. Either they are under codes
  nobody now remembers, or that data never reached these drives.

---

## 6. Provenance

| claim | source |
|---|---|
| 54 NCR sites, file counts | `docs/bern52/crd_catalog.csv` |
| NCKU velocities and sigmas | `toto_D/programs from NCKU/.../fit-h.out` |
| Taiwan site coordinates | `DATA0/wvfs/OUT/HL*.OUT`, `ESTIM` records |
| single-frequency observable | `DATA0/wvfs/OUT/GRA*.OUT`, `TYPES OF OBSERVATIONS: C1 L1 D1` |
| ionosphere model | `wvfs/STA/SIT*.CRD` header, "With Global ION model from CORS" |
| no ADDNEQ2 | `ls wvfs/OUT` — 32 program prefixes, none of them ADDNEQ2 |
| SOLD / CENT clusters | leader clustering at 1 km over all `.crd` in the archive |
