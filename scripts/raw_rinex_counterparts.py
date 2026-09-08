#!/usr/bin/env python3
"""How many raw receiver files have no RINEX counterpart?

CR-20260903 reserved this question because it decides whether decoding the
raw archive is worth doing at all. If almost every raw file was already
converted years ago, a decoding pipeline buys nothing.

WHAT COUNTS AS A COUNTERPART
A raw file and a RINEX file are counterparts if they are the same site on the
same day. This is matched on (site, year, day-of-year) parsed from FILENAMES,
which works here only because PHIVOLCS named these files by site.

THAT IS NOT TRUE OF THE FORMATS IN GENERAL. Trimble `.T0x` and Leica `.mNN`
names are receiver-assigned and carry a serial, not a site. It is true of THIS
archive, verified independently on both machines, and 5,717 files here are
serial-named exactly as the format spec would predict. Do not carry the
assumption to another corpus.

TWO TIERS, NEVER MERGED
  evidence   the filename carries site AND a full calendar date, so the match
             is exact. This is the number to quote.
  inference  the filename carries site and day-of-year but NO year, so the
             match is against any year. It systematically OVERSTATES coverage
             and must not be used for a decision.

WHAT THIS CANNOT ESTABLISH
  * Not that a counterpart is a GOOD conversion -- only that one exists.
  * Nothing about the serial-named files, which carry no site to match on.
  * Nothing about files whose counterpart exists outside this archive.

An earlier version of this analysis matched by DIRECTORY co-location and
reported 60.3% of raw files orphaned. That was wrong: the largest apparent
orphan block sits under a tree named `RAW/`, whose conversions live in a
parallel tree. It measured the filing convention, not the data.

Usage:
    scripts/raw_rinex_counterparts.py --files /path/to/file-listing.txt

The listing is one absolute path per line, produced once with `find` because
walking a 700k-file archive repeatedly is the wasteful way to do this.
"""
import re, os, collections, datetime
import argparse
_ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
_ap.add_argument("--files", required=True, help="file listing, one path per line")
LISTING = _ap.parse_args().files
COMP=re.compile(r'\.(gz|z|zip)$',re.I)
RNX =re.compile(r'^([A-Za-z0-9]{4})(\d{3})[a-z0-9]?\.(\d{2})[od]$',re.I)
RAWX=re.compile(r'\.(t0[0-9]|m[0-9]{2})$',re.I)

# --- full date in the name (site + year + month + day) -------------------
FULL = [
 re.compile(r'^([A-Za-z0-9]{4})_*(\d{4})(\d{2})(\d{2})\d{4}[A-Za-z]?\d?\.t0[0-9]$',re.I),
]
# --- day-of-year only, year NOT in the name ------------------------------
DOY = [
 re.compile(r'^([A-Za-z0-9]{4})(\d{3})[a-z]?[A-Za-z]?\.(t0[0-9]|m[0-9]{2})$',re.I),
 re.compile(r'^([A-Za-z0-9]{4})(\d{3})[a-z]\d+[A-Za-z]?\.(t0[0-9]|m[0-9]{2})$',re.I),
]
# --- site present but NO date at all -------------------------------------
NODATE = [ re.compile(r'^[a-z]{2}([A-Za-z0-9]{4})\d?\.m[0-9]{2}$') ]

rnx=set(); rnx_sd=set()
full=[]; doy=[]; nodate=0; serial=0; nraw=0
for ln in open(LISTING,encoding="utf-8",errors="replace"):
    b=COMP.sub("",os.path.basename(ln.rstrip("\n")))
    m=RNX.match(b)
    if m:
        s,d,yy=m.group(1).upper(),int(m.group(2)),int(m.group(3))
        rnx.add((s,1900+yy if yy>=80 else 2000+yy,d)); rnx_sd.add((s,d)); continue
    if not RAWX.search(b): continue
    nraw+=1
    for r in FULL:
        m=r.match(b)
        if m:
            try: full.append((m.group(1).upper(),int(m.group(2)),
                 datetime.date(int(m.group(2)),int(m.group(3)),int(m.group(4))).timetuple().tm_yday))
            except ValueError: pass
            break
    else:
        for r in DOY:
            m=r.match(b)
            if m: doy.append((m.group(1).upper(),int(m.group(2)))); break
        else:
            if any(r.match(b) for r in NODATE): nodate+=1
            else: serial+=1

print(f"  raw files                 : {nraw:,}")
print(f"  RINEX (site,year,doy) keys: {len(rnx):,}\n")
print(f"  FULL date in name         : {len(full):,}")
print(f"  DOY only                  : {len(doy):,}")
print(f"  site but NO date          : {nodate:,}")
print(f"  serial-named, no site     : {serial:,}")
print(f"  ---- accounted            : {len(full)+len(doy)+nodate+serial:,}")

hit=sum(1 for k in full if k in rnx)
print(f"\n=== EVIDENCE TIER (exact site+year+doy) ===")
print(f"  denominator               : {len(full):,}")
print(f"  has RINEX counterpart     : {hit:,}  ({hit/len(full)*100:.1f}%)")
print(f"  NO counterpart            : {len(full)-hit:,}  ({(len(full)-hit)/len(full)*100:.1f}%)")
h2=sum(1 for k in doy if k in rnx_sd)
print(f"\n=== INFERENCE TIER (site+doy, any year -- overstates) ===")
print(f"  no RINEX in any year      : {len(doy)-h2:,}  ({(len(doy)-h2)/len(doy)*100:.1f}%)")
miss=collections.Counter(k[0] for k in full if k not in rnx)
print(f"\n  un-converted by site      : {len(miss)} sites")
for s,c in miss.most_common(10): print(f"    {c:>6,}  {s}")
