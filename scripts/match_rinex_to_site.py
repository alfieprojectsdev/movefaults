#!/usr/bin/env python3
"""Attribute RINEX files to site codes by matching header position to the catalog.

Stage 3 of four. Stage 2 built `docs/bern52/crd_catalog.csv`, an index of
2,189 monument positions; this reads `APPROX POSITION XYZ` from a RINEX header
and asks which monument that is.

WHY POSITION AND NOT THE FILENAME
Trimble `.T0x` and Leica `.mNN` names carry a receiver serial, not a site.
Directory filing attributes ~97% of them, but that is inference from how
somebody once filed a directory. A header position is evidence from the data.

WHAT THE ANSWER IS WORTH
`APPROX POSITION` is a single-point position, good to roughly 100 m and
occasionally far worse — it is whatever the receiver believed at the time, and
a cold start can be kilometres out. So this is a *candidate* attribution with a
distance attached, not a determination:

  * `unique`    exactly one catalog site inside --radius. Trustworthy.
  * `aliases`   several codes inside --radius but all within --alias-m of each
                other. That is ONE monument under several names -- BLN2 and
                BLNA sit 3 m apart -- not an ambiguity. The nearest is reported
                and the rest listed as aliases. 625 catalog sites have a
                neighbour inside 100 m, so without this distinction almost
                every Philippine file is "ambiguous" and the tool says nothing.
  * `ambiguous` several codes inside --radius that are genuinely far apart, so
                the header cannot say which monument this is.
  * `none`      nothing inside --radius. Either an uncatalogued monument, or a
                header position bad enough to be useless. Distance to the
                nearest site is reported so the two can be told apart.
  * `no-header` no APPROX POSITION at all.

DISAGREEMENT WITH THE FILENAME IS THE POINT
Where a file already carries a site code (RINEX marker name, or the first four
characters of the filename), that is recorded alongside the match. Agreement
corroborates; disagreement is the finding stage 4 exists to report. Neither is
silently preferred.

NOT A COORDINATE TOOL. The catalog is an identification index whose frames and
epochs are deliberately unharmonised; see `docs/bern52/crd_catalog.md`.

Usage:
    scripts/match_rinex_to_site.py --root /srv/gnss-archive -o matches.csv
    scripts/match_rinex_to_site.py --root DIR --radius 200 --limit 500
"""
from __future__ import annotations

import argparse
import csv
import gzip
import math
import re
import sys
from collections import Counter
from pathlib import Path

CATALOG = Path("docs/bern52/crd_catalog.csv")

# Same bounds the catalog uses, for the same reason: it catches a truncated or
# garbage header in one check rather than trusting the format.
R_MIN, R_MAX = 6_353_000.0, 6_390_000.0

_APPROX = re.compile(r"^(.{60})APPROX POSITION XYZ")
_MARKER = re.compile(r"^(.{60})MARKER NAME")
# RINEX 2 (ssssDDD0.YYo) and RINEX 3 (SSSSMRCCC_..._MO.crx) both start with the
# 4-char site, which is why the filename is worth recording even when wrong.
_SITE_FROM_NAME = re.compile(r"^([A-Za-z0-9]{4})")


def open_text(path: Path):
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="ascii", errors="replace")
    return path.open("r", encoding="ascii", errors="replace")


def read_header(path: Path) -> tuple[tuple[float, float, float] | None, str]:
    """Return (xyz or None, marker name). Reads only the header."""
    xyz, marker = None, ""
    try:
        with open_text(path) as fh:
            for line in fh:
                if xyz is None:
                    m = _APPROX.match(line)
                    if m:
                        try:
                            v = [float(m.group(1)[i:i + 14]) for i in (0, 14, 28)]
                            xyz = (v[0], v[1], v[2])
                        except ValueError:
                            pass
                if not marker:
                    m = _MARKER.match(line)
                    if m:
                        marker = m.group(1).strip()[:4].upper()
                if "END OF HEADER" in line:
                    break
    except (OSError, EOFError):
        return None, ""
    return xyz, marker


def load_catalog(path: Path) -> list[tuple[str, float, float, float]]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(ln for ln in fh if not ln.startswith("#")):
            try:
                rows.append((r["site"], float(r["x"]), float(r["y"]), float(r["z"])))
            except (KeyError, ValueError):
                continue
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", type=Path, action="append", required=True)
    ap.add_argument("--catalog", type=Path, default=CATALOG)
    ap.add_argument("--radius", type=float, default=150.0,
                    help="metres; a header position is good to ~100 m, so the "
                         "default allows for that plus a little (default 150)")
    ap.add_argument("--alias-m", type=float, default=50.0,
                    help="candidates within this of each other are treated as "
                         "one monument under several codes, not as an "
                         "ambiguity (default 50)")
    ap.add_argument("--limit", type=int, help="stop after N files (for a trial run)")
    ap.add_argument("-o", "--output", type=Path, default=Path("rinex_matches.csv"))
    args = ap.parse_args()

    cat = load_catalog(args.catalog)
    known = {c[0] for c in cat}
    bysite = {c[0]: (c[1], c[2], c[3]) for c in cat}
    if not cat:
        print(f"FATAL: no catalog rows in {args.catalog}", file=sys.stderr)
        return 1
    print(f"  catalog sites: {len(cat)}   match radius: {args.radius:g} m")

    pats = ("*.[0-9][0-9]o", "*.[0-9][0-9]O", "*.[0-9][0-9]d", "*.rnx", "*.crx",
            "*.crx.gz", "*.rnx.gz")
    files = sorted({p for r in args.root for pat in pats for p in r.rglob(pat)
                    if p.is_file()})
    if args.limit:
        files = files[:args.limit]
    print(f"  RINEX files: {len(files)}")

    verdicts: Counter[str] = Counter()
    agree = disagree = no_name = new_attr = 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as fh:
        fh.write("# RINEX -> site attribution by header position. CANDIDATES, not\n"
                 "# determinations: APPROX POSITION is a single-point fix good to\n"
                 "# ~100 m and sometimes far worse. See match_rinex_to_site.py.\n")
        w = csv.writer(fh)
        w.writerow(["path", "verdict", "matched_site", "distance_m",
                    "n_within_radius", "alternatives", "name_site",
                    "marker_site", "agrees", "claimed_site", "claimed_m"])
        for p in files:
            xyz, marker = read_header(p)
            nm = _SITE_FROM_NAME.match(p.name)
            name_site = nm.group(1).upper() if nm else ""

            if xyz is None:
                verdicts["no-header"] += 1
                w.writerow([p, "no-header", "", "", 0, "", name_site, marker, "", "", ""])
                continue
            if not (R_MIN <= math.dist((0, 0, 0), xyz) <= R_MAX):
                verdicts["bad-position"] += 1
                w.writerow([p, "bad-position", "", "", 0, "", name_site, marker,
                            "", "", ""])
                continue

            near = sorted(((math.dist(xyz, (x, y, z)), s) for s, x, y, z in cat))
            within = [(d, s) for d, s in near if d <= args.radius]
            if len(within) == 1:
                verdict, site, dist = "unique", within[0][1], within[0][0]
            elif len(within) > 1:
                # Are the candidates one monument or several? Compare them to
                # each other, not to the header position -- the header is the
                # imprecise term here, and the catalog positions are not.
                cand = {s_: (x, y, z) for s_, x, y, z in cat
                        if s_ in {s2 for _, s2 in within}}
                pts = list(cand.values())
                extent = max(math.dist(a, b) for a in pts for b in pts)
                verdict = "aliases" if extent <= args.alias_m else "ambiguous"
                site, dist = within[0][1], within[0][0]
                # When the candidates are one monument under several codes, the
                # position cannot choose between them -- they are 3 m apart and
                # the header is good to ~100 m. If the file's own marker or
                # name is one of those codes, that is the code to report:
                # picking the nearest instead let 6 BLNA files be labelled BLN2
                # on a 0.3 m margin, and called it a disagreement.
                #
                # This is not deferring to the filename. The position has
                # already decided WHICH MONUMENT; the name only picks among
                # names the position has confirmed.
                if verdict == "aliases":
                    # Check BOTH the marker and the filename against the
                    # confirmed candidates, and take whichever matches. An
                    # earlier version preferred the marker unconditionally,
                    # which let junk markers -- literal "SITE", "TEMP" -- beat
                    # a filename that named a candidate exactly, and reported
                    # 65 such files as disagreements.
                    for cand_code in (marker, name_site):
                        if not cand_code:
                            continue
                        hit = next((c for c in within if c[1] == cand_code), None)
                        if hit:
                            dist, site = hit
                            break
            else:
                verdict, site, dist = "none", "", near[0][0]

            verdicts[verdict] += 1
            # Recorded, never used to decide: a filename that disagrees with the
            # position is exactly what stage 4 is for.
            # Agreement means the site matched one of the names the file
            # carries, not that it matched the one we happened to prefer.
            refs = {r for r in (marker, name_site) if r}
            # A name only counts as contradicting evidence if it names a site
            # the catalog knows. "TEMP", "DEFA" and receiver-assigned numbers
            # like 7239 are not claims about identity, so a position that
            # disagrees with them is not a conflict -- it is the attribution
            # this stage exists to produce. Tested against the catalog rather
            # than a hardcoded placeholder list, because campaign point numbers
            # such as 0194 and 02G1 ARE legitimate site codes.
            informative = {r for r in refs if r in known}
            # How far is the header from the site the file CLAIMS? Without this
            # a conflict cannot be read. A position 35 m from one monument and
            # 2 km from the claimed one is decisive; 35 m versus 45 m is inside
            # the ~100 m the header is worth and decides nothing.
            claimed = next(iter(sorted(informative)), "")
            claimed_d = math.dist(xyz, bysite[claimed]) if claimed else None
            if verdict in ("unique", "aliases") and informative:
                if site in informative:
                    agree += 1
                else:
                    disagree += 1
            elif verdict in ("unique", "aliases") and refs:
                new_attr += 1
            elif verdict in ("unique", "aliases"):
                no_name += 1

            w.writerow([p, verdict, site, f"{dist:.1f}" if dist else "",
                        len(within), "|".join(s for _, s in within[1:4]),
                        name_site, marker,
                        "" if verdict not in ("unique", "aliases")
                        else ("" if not informative
                              else ("yes" if site in informative else "NO")),
                        claimed, f"{claimed_d:.1f}" if claimed_d is not None else ""])

    print(f"  wrote {args.output}\n")
    for v, n in verdicts.most_common():
        print(f"    {n:>7}  {v}")
    tot = sum(verdicts.values()) or 1
    attributed = verdicts["unique"] + verdicts["aliases"]
    print(f"\n  attributed to one monument: {attributed} "
          f"({100 * attributed / tot:.1f}%)  "
          f"[{verdicts['unique']} single-code, {verdicts['aliases']} aliased]")
    print(f"  of those, a name the catalog knows: {agree + disagree}"
          f"  -- agrees {agree}, DISAGREES {disagree}")
    print(f"  name not a known site (position supplies the identity): {new_attr}")
    print(f"  no name at all: {no_name}")
    if disagree:
        print("  -> disagreements are the stage 4 report, not errors to suppress")
    return 0


if __name__ == "__main__":
    sys.exit(main())
