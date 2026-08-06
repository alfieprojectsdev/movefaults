# Ocean-loading coefficients for the seven IGS fiducials

`LUZON.BLQ` covers the 135 local PHIVOLCS stations and **none of the seven IGS
fiducials** the network uses for datum control. With those staged, `GPSEDT`
stops:

```
*** SR GTOCNL: OCEAN LOADING CORRECTION VALUES NOT FOUND
               STATION NAME : ALIC 50137M001
```

No `.BLQ` anywhere in the 5.2 capture contains ALIC, so the coefficients were
never computed for those sites. They are free from the Chalmers/Onsala service,
which delivers **by email** — so one manual step is unavoidable. Everything
either side of it is prepared here.

## ⚠ Match the existing settings — do not use the service defaults

The 135 stations already in `LUZON.BLQ` were computed with a specific
configuration, recorded in the file's own header:

```
$$ Ocean tide model: FES2004
$$ CMC:  NO   (corr.tide centre of mass)
$$ Gutenberg-Bullen Greens function is used
```

**Request FES2004, not a newer model.** Coefficients on a different ocean model
would put the seven datum stations on a different basis from the 135 they
constrain — a systematic inconsistency that does not announce itself in the
file and is painful to trace afterwards. A newer model is better *only* if the
whole file is recomputed, which is a separate decision.

## The request

Paste `REQUEST_fiducials.txt`:

```
AIRA -3530185.90159 4118797.17811 3344036.67302
ALIC -4052052.79683 4212835.97064 -2545104.50221
DAEJ -3120042.45801 4084614.65640 3764026.77258
DARW -4091359.66844 4684606.39892 -1408579.03120
MCIL -5227187.43755 2551881.35064 2607618.30816
PIMO -3186293.50508 5286624.44981 1601158.39629
PNGM -5367943.20000 3437431.20000 -225886.00000
```

These are **ECEF XYZ taken directly from `$D/REF54/LUZON.CRD`** — the same
coordinates the BPE processes. The form accepts `name X Y Z` as an alternative
to lon/lat/height, so no geodetic conversion is performed and the
"I-never-swap-lon/lat" ambiguity does not arise.

Names are bare 4-character codes, matching how the existing blocks are written
(`  ABUY               ABUY`).

## Form settings

| Field | Value | Why |
|---|---|---|
| Ocean tide model | **FES2004** | matches the existing 135 — see above |
| Loading phenomenon | **vertical and horizontal displacements** | not gravity/tilt |
| Greens function | **elastic (Farrell, 1972)** | Farrell 1972 uses the Gutenberg-Bullen earth model named in the header |
| CMC correction | **NO** | header records `CMC: NO` |
| Output format | **BLQ** | not HARPOS |
| Plot | NO | not needed |
| Email | your address | results arrive as plain text |

Portal: <https://barre.oso.chalmers.se/loading/l.php>
(The older Holt portal has been down with a mail fault since 2024-05.)

If nothing arrives within a few hours, check the
[queue](https://barre.oso.chalmers.se/loading/queue.php) and the
[why-not criteria](https://barre.oso.chalmers.se/loading/wncace.html).

## Merging the reply

```bash
scripts/merge_blq.py --blq $D/REF54/LUZON.BLQ --new onsala-reply.txt          # dry run
scripts/merge_blq.py --blq $D/REF54/LUZON.BLQ --new onsala-reply.txt --apply
cp $D/REF54/LUZON.BLQ $P/LUZON/STA/LUZON.BLQ
```

It refuses to add a station already present (a duplicate block is worse than a
missing one — which of two conflicting entries Bernese honours is not evident
from the file), validates each incoming block as six rows of eleven values, and
backs up first.

**Record the model actually used** in the commit message when the merged file
lands. It is part of the provenance of every coordinate computed afterwards, and
the file header will say so for the new blocks but not retrospectively for the
old ones.

## Why this matters

Without the fiducials there are no IGS reference stations in the solution, so
`HELMR1` reports `NO REDUNDANCY` and the result has no datum verification —
runbook §4b.7. With them, and with consistent ocean loading, the 31-day run
becomes both possible and meaningful.

## Citation

If the results are used in published work, the service asks to be cited as
`https://barre.oso.chalmers.se/loading/l.php`, naming M.S. Bos and
H.-G. Scherneck.
