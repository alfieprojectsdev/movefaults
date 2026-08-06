# Ocean-loading coefficients for the IGS fiducials

`LUZON.BLQ` covers the 135 local PHIVOLCS stations and **none of the seven IGS
fiducials** the LUZON network uses as datum control. With those staged,
`GPSEDT` stops:

```
*** SR GTOCNL: OCEAN LOADING CORRECTION VALUES NOT FOUND
               STATION NAME : ALIC 50137M001
```

No `.BLQ` anywhere in the 5.2 capture contains ALIC, so the coefficients were
never computed for those sites. They are free from the Chalmers/Onsala OTL
service — **but that service delivers by email**, so one manual step is
unavoidable.

## What is prepared here

`REQUEST_fiducials.txt` — the seven stations as `longitude latitude height name`,
the format the request form expects. Coordinates are taken from
`$D/REF54/LUZON.CRD`, so the coefficients are computed for exactly the points
the BPE processes. Six of the seven were cross-checked against Abegail's own
`F1_251210.SNX` `SITE/ID` block and agree to the arcsecond.

## The manual step

1. Open <https://barre.oso.chalmers.se/loading/l.php>
   (the older Holt portal is down — a mail-system fault since 2024-05.)
2. Paste the contents of `REQUEST_fiducials.txt` into the coordinate box.
3. Ocean tide model: **FES2014b** unless there is a reason to match an older
   run. Note what you chose — the model is part of the provenance.
4. Output format: **BLQ**, with radial and horizontal components.
5. Give your email address; the reply arrives as plain text.

## Then

Save the reply and merge:

```bash
scripts/merge_blq.py --blq $D/REF54/LUZON.BLQ --new onsala-reply.txt          # dry run
scripts/merge_blq.py --blq $D/REF54/LUZON.BLQ --new onsala-reply.txt --apply
```

It refuses to add a station already present (a duplicate BLQ block is worse than
a missing one — which of two conflicting entries wins is not evident from the
file), checks every incoming block is 6 rows x 11 values, and backs up first.

Afterwards copy the updated file into the campaign:

```bash
cp $D/REF54/LUZON.BLQ $P/LUZON/STA/LUZON.BLQ
```

## Why the fiducials matter

Without them the run has no IGS reference stations, so `HELMR1` reports
`NO REDUNDANCY` and the solution has no datum verification — see runbook §4b.7.
