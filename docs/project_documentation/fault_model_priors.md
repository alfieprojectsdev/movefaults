# Fault model priors: defaults and ranges for 2-D profile models

**Status: literature defaults, not yet signed off.** These are starting values
for the 2-D dislocation profile models (screw dislocation or Okada, strike-slip,
plus block motion) of the Philippine Fault. They come from a literature review
done on 2026-11-13. A geologist should review this page once before the console
offers its values as defaults (`docs/SETTLED.md`, section 6). The person running
a model can always change them.

Read with:

- [`dislocation_model_results.md`](dislocation_model_results.md): what PHIVOLCS
  has already run, segment by segment.
- [`inversion_method_decision.md`](inversion_method_decision.md): the method
  choice still waiting on PHIVOLCS.
- [`analysis_port_assessment.md`](analysis_port_assessment.md): the defects
  found in the MATLAB being ported.

## How much to trust each number

Every source is tagged with how far it was checked:

| Tag | Meaning |
|---|---|
| [F] | full text read |
| [A] | abstract read, body not read |
| [S] | search snippet, or a citation inside another paper; not checked against the original |
| [M] | from memory, not verified |

Treat [S] and [M] values as leads, not priors, until someone reads the original.

Terms used below:

- **Locking depth D:** the depth above which the fault is stuck between
  earthquakes. Below it the fault slips steadily.
- **Creep:** the fault slipping steadily at or near the surface, with no
  earthquakes. A creeping fault shows a sharp step in velocity across the trace,
  not the smooth S-curve of a locked one.
- **Block rate s:** the far-field difference in fault-parallel velocity across
  the fault.
- **Edge position x0:** where the bottom of the locked part sits, measured
  horizontally from the mapped trace. For a dipping fault x0 = x_trace + D·cot(dip).

## What a profile of 10–15 stations can resolve

Such a profile supports **three or four free parameters**: s, a constant offset,
and either D or x0, rarely both. Fix the rest.

- **D needs two groups of stations:** some within about D/2 of the fault, and
  some far out (more than about 50 km). Otherwise D trades against s along one
  long valley of equal misfit. On the Imperial fault, D = 4 km at 32 mm/yr fits
  as well as D = 10 km at 44 mm/yr (Smith-Konter et al. 2011 [F]).
- **Dip and trace offset can't be separated.** Only x0 changes the surface
  velocities (Lindsey & Fialko 2013 [F]). At D = 15 km, a dip of 65° moves the
  edge 7 km, more than the whole ±3 km offset grid. **Fix dip at 90° and estimate
  x0**, with a sensitivity run at the published dip.
- **Width isn't resolvable.** If it is the down-dip extent of the deep slipping
  part, fix it at effectively infinite (at least 10 times the profile
  half-length). If it stands for a creep depth, only D minus the creep depth is
  resolvable.
- **Creep depth isn't resolvable** even with good near-fault data (Lindsey &
  Fialko 2013 [F]). Fix it and say so.
- **Global prior for D when nothing local exists:** 14 ± 7 km, from 187 estimates
  (Wright et al. 2013 [F]).
- **Before trusting a fit, run a synthetic test on the real station layout:**
  model the defaults, add realistic noise, refit, and see which parameters come
  back.

## How to choose and report the best model

1. **Fit three models on every profile:** no fault (constant velocity), a pure
   creep step, and a locked fault. Report how much better the preferred model
   fits (Δχ²) than each of the other two.
2. **Take the minimum-χ² model.** Never pick the model whose reduced χ² is
   closest to 1. That rule changes its answer when every σ is scaled by the same
   factor, and with 8–11 degrees of freedom reduced χ² scatters by about ±0.5
   anyway (Andrae et al. 2010 [F]). On Leyte, a σ error alone changed every
   Northern Leyte pick under that rule (gps3 session log, section 42).
3. **Give every velocity σ a floor of about 0.5 mm/yr,** so that one precise
   continuous station doesn't dominate the fit (Lindsey & Fialko 2013 [F]). If
   χ²/(n − p) is still above 1, scale the uncertainties by it.
4. **Quote intervals from the χ² surface.** Δχ² of 1 is the 68% interval for one
   parameter, and 4 is the 95% interval [M, standard results]. With linear terms
   solved directly at each grid node, a dense grid is exact for three or four
   parameters. Use MCMC only beyond that.
5. **Prefer leaving one station out at a time (jackknife) to resampling
   stations,** with only 12–15 stations. A resample drops about 37% of the sites,
   sometimes every near-fault one.
6. **A parameter at the edge of its range:** first decide whether the edge is
   artificial (a grid limit) or physical (D = 0, dip = 90°). Widen an artificial
   one. For a physical one, report a one-sided bound such as "D < 4 km at 95%".
7. **Show the prior next to the result.** Where they match, the data didn't
   constrain the parameter, and the report must say so.

Projecting velocities onto the profile needs the east and north errors
propagated with the profile azimuth, not the total error scaled by the angle to
the velocity (the defect in every copy of `velproj_loop.m`). The east–north
correlation term matters except when the azimuth is near 0° or 90°.

## Defaults by segment

Ranges are plausible ranges, not confidence intervals. "Avoid" means velocity
data from that window will be biased by an earthquake or its aftermath; either
exclude it or model the step.

### Northern Leyte (about 11.0–11.5°N; PHIVOLCS profile azimuth 55°)

**This segment mostly creeps, so a fault locked to some depth is the wrong model
here.** InSAR shows creep to the surface at about the full rate along about
100 km, 33 ± 11 mm/yr (Fukushima et al. 2019 [F]). The exception is a locked
patch about 20 km long at Tongonan (11.08–11.20°N), locked from 0 to about 7 km,
which ruptured in the 2017 Mw 6.5 earthquake (Dianala et al. 2020 [F]).

| Parameter | Default | Range | Sources | Confidence |
|---|---|---|---|---|
| Strike | 325° | 320–330° | Fukushima [F]; Yang 2018 [S]; USGS [S] | High |
| Trace offset x0 | 0 | ±1 km north of 11.2°N; ±3 km, or two strands 2 km apart, at Tongonan | Dianala relay zone 2–4 km [F] | Medium |
| Dip | 90°, fixed | 72–90°, east-dipping | Fukushima 74° [F]; Yang 78.5° [S]; Dianala 90° [F] | Medium |
| Locking depth D | About 0 on the creeping trace; 7 km at Tongonan | 0–3 km; 5–10 km at Tongonan | Dianala [F] | High (creeping) / Medium |
| Creep rate | About the block rate; 0 at Tongonan | 20–55 mm/yr | Fukushima 33 ± 11 [F]; Okur 2025 35–55 [A]; Tsutsumi & Perez 2024 20.9 ± 4.3 [A] | Medium |
| Block rate s | 34 mm/yr | 20–45 mm/yr | Duquesnoy 35 ± 4 (via Rangin) [F]; Bacolcol 36 ± 2 [A]; geologic 19–25 [S] | Medium |
| Avoid | 2017-07-06 to at least 2018-06. Don't combine velocities from before 2013 with ones from after 2016 | | | Medium |
| Drop or model | Sites within about 5 km of the Tongonan geothermal field (11.1–11.2°N, 124.6–124.7°E), which subsides 2.5–3.5 cm/yr | | Dianala, Fukushima [F] | High |

Dianala et al.'s deep rate of 33 ± 2 mm/yr is driven by the prior they imposed
(centred on 30 mm/yr). It is not an independent check on s.

PHIVOLCS' past runs fit this picture: the 2023 run found D = 1 km, effectively a
creep step, and the 2021 run's block rate of 47 (40–50) mm/yr sat at the top of
the grid (`dislocation_model_results.md`).

### Southern Leyte (south of the 11°N step; PHIVOLCS profile azimuth 73°)

**This is the least-studied part of the fault south of Luzon.** No onshore
strike, creep rate, locking depth or far-field rate has been published for the
far south. The central segment (about 10.6–11.0°N) has InSAR creep.

| Parameter | Default | Range | Sources | Confidence |
|---|---|---|---|---|
| Strike | Measure from the trace; about 335–343° | 330–345° | Island-scale N25°W [F] | Low |
| Trace offset x0 | 0 | ±3 km, widen to ±5 km if it hits the edge | Off-trace faulting [F] | Medium–Low |
| Dip | 90°, fixed | 70–90° | Northern analogues only | Low |
| Locking depth D | 10 km if locked; about 0 if creeping | 0–20 km, test to 25 | Wright 2013 global prior [F] | Low |
| Creep rate | Central segment: 15–30 mm/yr. Far south: 0, left free | 0 to s | Fukushima [F]; Tsutsumi & Perez [A]; Hung, abstract: no creep step [A]; Sharma 2026 [S] | Low |
| Block rate s | 30 mm/yr | 15–45 mm/yr | Leyte 33–37 to the north, Surigao 21–27.5 to the south (Rangin [F]; Aurelio 2000 [F]) | Low |
| Avoid | Steps on 2013-10-15 (Bohol Mw 7.1), 2017-02-10 (Surigao Mw 6.5) and 2017-07-06 (Ormoc) for nearby stations | | Tobita 2015 [F] | Medium |

Check the 73° profile azimuth against the local trace before projecting:
a fault-normal profile on a 343° trace would be 73°, but nothing published
confirms that strike.

PHIVOLCS' 2021 run gave D = 96 (90–100) km and a back-slip of 0.96
(−36 to 2.2) mm/yr. That means no locked fault was resolved, not a 96 km locking
depth. The re-run on 2026-11-12 data (gps3 session log, section 42) fits badly
with either σ: the best reduced χ² is 42 to 177, and depth and width picks
spread over the whole grid. Over 1,000 resamples its picks sit at dip 90° in
72–80% and at dip 65° in 8–24%, depending on the σ formula, and never at either
block-rate limit. Dip 90° is a physical limit (a vertical fault); dip 65° is dip
absorbing an edge shift, which is why dip should be fixed and x0 estimated. A
creep-step model is the first thing to try.
Bacolcol et al. (2012), as tabulated in PHIVOLCS' compilation of results (`dislocation_model_results.md`), gives D 13 km, dip 80°
and s 30 mm/yr; the publication itself hasn't been located [S].

### Masbate

**A transition zone:** shallow creep, with repeated Mw 6+ earthquakes (2003,
2020) on overlapping patches (Besana & Ando 2005 [F]; Sta. Rita et al. 2024 [F]).

| Parameter | Default | Range | Sources | Confidence |
|---|---|---|---|---|
| Strike | 320° | 310–330° | Sta. Rita [F]; Besana & Ando [F] | Medium–High |
| Trace offset x0 | 0 | ±5 km (inference; the Uson strand runs parallel) | | Low |
| Dip | 90°, fixed | 75–90° | "Sub-vertical" [F] | Medium–Low |
| Locking depth D | 15 km | 10–25 km | 2003 and 2020 hypocentres at 21–22 km [F] | Low |
| Creep rate | 10 mm/yr | 5–17 mm/yr | Alignment arrays 7–17 [S/F] | Low–Medium |
| Creep depth | 3 km, assumed | 0–5 km | None published | Very low |
| Block rate s | 33 mm/yr | 20–40 mm/yr | Llamas 2025 preprint [A]; Rangin about 35 [F]; Bacolcol 23 [A/F] | Medium–Low |
| Avoid | 2003-02 to 2004-02, and 2020-07 to about 2022. Afterslip in the first 31 days after 2020 was at least a quarter of the earthquake's moment | | Sta. Rita [F] | Medium |

Bacolcol's GPS figure of 23 mm/yr conflicts with 33–35. Whether it is a creep
rate or a far-field rate, and whether its uncertainty is ±2 or ±11, isn't clear
from the secondary citations.

### Central Luzon (Digdig; the 1990 Mw 7.7 rupture)

**Locked to about 20 km, with no shallow creep.** The slip rate is disputed by a
factor of two to four:

- geologic 9–17 mm/yr [S];
- a viscoelastic reinterpretation of the post-1990 GPS, 15–22 mm/yr (Beavan
  et al. 2001 [A]);
- elastic GPS models, 24–37 mm/yr (Hsu 2016 [F]; Yu 2013 [F]).

Beavan et al. attribute the gap to deformation lingering after 1990.

| Parameter | Default | Range | Sources | Confidence |
|---|---|---|---|---|
| Strike | 334° | 325–345° | 1990 mechanism 153–155° [A/S] | Medium |
| Trace offset x0 | 0 | ±10 km (inference), or two dislocations (Digdig and San Jose) | Braided strands [F/S] | Low |
| Dip | 90°, fixed | 75–90° | Velasco 89° [A]; Yu 85–89° [F]; Hsu 90° [F] | High |
| Locking depth D | 20 km | 10–30 km | Yu 15 (10–26) [F]; Hsu 20 [F]; Galgana 25 [F] | Medium–High |
| Shallow creep | 0 | 0–5 mm/yr | Yu, closely spaced station pairs [F] | Medium |
| Block rate s | 25 mm/yr | 10–45 mm/yr | as above | Low–Medium |
| Avoid | Data before 2000; prefer data after 2010 | | Beavan [A]; Yu [F] | Medium |

A fit of velocities from after 2010 would settle whether the elastic rate of
about 37 mm/yr was an artefact of the 1990 earthquake.

### Guinayangan (Bondoc Peninsula / Ragay Gulf, southern Luzon)

**Locked.** No segment-specific defaults were compiled. Regional rates are about
35 mm/yr (Rangin et al. 1999 [F]) and 40 (33–52) mm/yr on Yu et al.'s southern
transect, where dip was 70° (52–90) [F]. Masbate's description calls Guinayangan
the locked segment north of the Masbate transition (Besana & Ando 2005 [F]).
PHIVOLCS has four runs on record (`dislocation_model_results.md`). Until a review
covers it, use Central Luzon's form (locked, dip 90°, D 15–20 km) with
s 35 mm/yr (25–45).

### Mindanao

**A 2-D profile suits only the northern third,** from about 8.6°N to 9.8°N (the
Surigao, Esperanza and northern Agusan Marsh segments). Further south, parallel
strands, the Mati and Lianga branches, the Cotabato fault system and the trench
call for a 3-D block model. The rate falls southward, from about 20 mm/yr at
Surigao to about 10 near Davao. The north creeps: two campaign sites 10 km apart
on the Surigao segment move 23.3 mm/yr relative to each other (Ohkura et al.
2015 [F]).

| Parameter | Surigao–Esperanza (8.8–10°N) | Agusan Marsh (8–8.8°N) | Compostela–Caraga–Mati (6.8–8°N) |
|---|---|---|---|
| Strike | 160–165° | 165–170° | about 180°; Caraga 140–150° |
| Trace offset x0 | ±2 km; ±3–5 km at Lake Mainit | ±2 km; ±5 km near the end steps | ±10 km, or two dislocations |
| Dip | 90°, fixed (75–90°, either way) | 90°, fixed | 90°, fixed |
| Locking depth D | free, 0–20 km | 15 km (10–20) | 15 km (10–20) |
| Creep rate | free, 0–25 mm/yr (default 15) | free, 0 to s | 0–3 mm/yr |
| Block rate s | 20 mm/yr (10–30) | 15 mm/yr (5–25) | 10 mm/yr (3–22) |
| Extra term | linear gradient (block rotation) | linear gradient | prefer a 3-D block model |
| Avoid | step on 2017-02-10; step on 2023-12-02 plus decay, or stop at 2023-11 | 2023-12-02 step plus decay, or stop at 2023-11 | 2019-10 to 2019-12 steps at western sites |

Sources: Perez et al. 2015 [F] for segment geometry, Aurelio 2000 [F],
Rangin 1999 [F], Tobita 2015 [F], Ohkura 2015 [F]. Confidence is low throughout:
no locking depth has been measured on Mindanao, and Rangin's 15 km is borrowed
from Luzon. Marfito et al. 2022 give 3–5 mm/yr for Surigao, but neither source
they cite contains it; it is not used here.

## Changes to the current Leyte grids

| Parameter | Current grid | Change to |
|---|---|---|
| Model form | locked fault plus block | three models on every profile: none, creep step, locked |
| Locking depth | 0–15 km | North: keep. South: 0–25 km |
| Width | 0–15 km, free | fixed (see "What a profile can resolve") |
| Dip | 65–90°, free | fixed at 90°; sensitivity run at 75° east |
| Block rate | 30–50 mm/yr | North 20–45 (default 34); South 15–45 (default 30) |
| Trace offset | ±1 km (N), ±3 km (S) | estimate x0: ±1 km north of 11.2°N, ±3 km at Tongonan, ±5 km south |
| Selection | reduced χ² closest to 1 | minimum χ² |

## Still open

- The full texts of Sharma et al. 2026 and Okur et al. 2025, which bear directly
  on Leyte creep by segment and by decade.
- Bacolcol et al. (2012), cited for several segments in PHIVOLCS' compilation,
  hasn't been located.
- Afterslip decay times for 2017 Ormoc, 2020 Masbate and 2023 Hinatuan are
  unpublished; the "avoid" windows above are inferences.
- A geologist's sign-off on this page.

## Sources

| Source | DOI | Read as |
|---|---|---|
| Andrae, Schulze-Hartung & Melchior 2010 | [arXiv:1012.3754](https://arxiv.org/abs/1012.3754) | [F] |
| Aurelio 2000, Island Arc 9 | [10.1046/j.1440-1738.2000.00304.x](https://doi.org/10.1046/j.1440-1738.2000.00304.x) | [F] |
| Bacolcol et al. 2006, JpGU T225-003 | abstract | [A] |
| Barrier, Huchon & Aurelio 1991, Geology 19 | 10.1130/0091-7613(1991)019<0032:PFAKFP>2.3.CO;2 | [S] |
| Beavan et al. 2001, G³ 2 | [10.1029/2000GC000100](https://doi.org/10.1029/2000GC000100) | [A] |
| Besana & Ando 2005, EPS 57 | [10.1186/BF03351877](https://doi.org/10.1186/BF03351877) | [F] |
| Dianala et al. 2020, JGR 125 | [10.1029/2020JB020052](https://doi.org/10.1029/2020JB020052) | [F] |
| Duquesnoy et al. 1994, GRL 21 | [10.1029/94GL00640](https://doi.org/10.1029/94GL00640) | [A] |
| Fukushima et al. 2019, EPS 71 | [10.1186/s40623-019-1096-5](https://doi.org/10.1186/s40623-019-1096-5) | [F] |
| Galgana et al. 2007, Tectonophysics 432 | [10.1016/j.tecto.2006.12.001](https://doi.org/10.1016/j.tecto.2006.12.001) | [F] |
| Hsu et al. 2016, JGR 121 | [10.1002/2016JB013082](https://doi.org/10.1002/2016JB013082) | [F] |
| Jolivet, Bürgmann & Houlié 2009, EPSL 288 | [10.1016/j.epsl.2009.09.014](https://doi.org/10.1016/j.epsl.2009.09.014) | [F] |
| Lindsey & Fialko 2013, JGR 118 | [10.1029/2012JB009358](https://doi.org/10.1029/2012JB009358) | [F] |
| Llamas et al. 2024, Tectonics | [10.1029/2023TC008106](https://doi.org/10.1029/2023TC008106) | [A] |
| Llamas et al. 2025, ESSOAr preprint | [10.22541/essoar.176339892.29035500/v1](https://doi.org/10.22541/essoar.176339892.29035500/v1) | [A] |
| Marfito, Llamas & Aurelio 2022, Front. Earth Sci. 10 | [10.3389/feart.2022.799803](https://doi.org/10.3389/feart.2022.799803) | [F] |
| Ohkura et al. 2015, JDR 10 | [10.20965/jdr.2015.p0059](https://doi.org/10.20965/jdr.2015.p0059) | [F] |
| Okada 1985, BSSA 75 | [10.1785/BSSA0750041135](https://doi.org/10.1785/BSSA0750041135) | [M] |
| Okur et al. 2025, PEPS | [10.1186/s40645-025-00758-8](https://doi.org/10.1186/s40645-025-00758-8) | [A] |
| Perez et al. 2015, JDR 10 | [10.20965/jdr.2015.p0074](https://doi.org/10.20965/jdr.2015.p0074) | [F] |
| Perez & Tsutsumi 2017, Tectonophysics 699 | [10.1016/j.tecto.2017.02.001](https://doi.org/10.1016/j.tecto.2017.02.001) | [A] |
| Rangin et al. 1999, GJI 139 | [10.1046/j.1365-246x.1999.00969.x](https://doi.org/10.1046/j.1365-246x.1999.00969.x) | [F] |
| Savage & Burford 1973, JGR 78 | [10.1029/JB078i005p00832](https://doi.org/10.1029/JB078i005p00832) | [M] |
| Sharma et al. 2026, Remote Sens. Environ. | [10.1016/j.rse.2026.115273](https://doi.org/10.1016/j.rse.2026.115273) | [S] |
| Smith-Konter, Sandwell & Shearer 2011, JGR 116 | [10.1029/2010JB008117](https://doi.org/10.1029/2010JB008117) | [F] |
| Sta. Rita, Valkaniotis & Lagmay 2024, NHESS 24 | [10.5194/nhess-24-1135-2024](https://doi.org/10.5194/nhess-24-1135-2024) | [F] |
| Tobita et al. 2015, JDR 10 | [10.20965/jdr.2015.p0067](https://doi.org/10.20965/jdr.2015.p0067) | [F] |
| Tsutsumi & Perez 2024, Geosci. Lett. 11 | [10.1186/s40562-024-00367-1](https://doi.org/10.1186/s40562-024-00367-1) | [A] |
| Velasco et al. 1996, JGR 101 | [10.1029/96JB02290](https://doi.org/10.1029/96JB02290) | [A] |
| Wright et al. 2013, Tectonophysics 609 | [10.1016/j.tecto.2013.07.029](https://doi.org/10.1016/j.tecto.2013.07.029) | [F] |
| Yang et al. 2018, GRL 45 | [10.1002/2017GL076417](https://doi.org/10.1002/2017GL076417) | [S] |
| Yu et al. 2013, JAES 65 | [10.1016/j.jseaes.2010.12.007](https://doi.org/10.1016/j.jseaes.2010.12.007) | [F] |
