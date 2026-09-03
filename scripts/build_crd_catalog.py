#!/usr/bin/env python3
"""Build a site-code -> coordinate index from Bernese CRD files.

WHAT THIS IS
An **identification index**, not a coordinate product. Its one job is to answer
"which monument is this?" from an approximate position, to about 100 m.

WHY IT EXISTS
`drive-arch` cannot attribute 28,803 raw receiver files on DATA0 to site codes:
Trimble `.T0x` and Leica `.mNN` filenames carry a receiver serial, not a site
(`36252110.t01` names the receiver and nothing else). Directory filing guesses
~97% of them, but that is inference from how somebody once filed a directory.

The evidence-based route is raw -> RINEX -> `APPROX POSITION XYZ` from the
header -> match against known monument coordinates -> site code. This builds the
catalog that match runs against. It is stage 2 of four; stages 1, 3 and 4 are
separate work.

WHAT IT IS NOT, AND WILL NOT BECOME
**Do not use these as authoritative station coordinates.** The inputs span
WGS-84, ITRF2005/2008/2014 and IGS20, at epochs from the 1990s to 2025, and are
deliberately NOT harmonised. Frame differences are decimetre-level and 30 years
of Philippine Mobile Belt motion at up to ~8 cm/yr is ~2.5 m -- both three
orders of magnitude below the ~100 m resolution this problem needs, which is
itself set by the accuracy of a single-point position in a RINEX header.
Building a transformation chain would be real work for zero gain here.

Rows derived from CODSPP are metre-level by nature; `best_kind` says so per
site, so a consumer can tell a millimetre row from a metre one.

CAUTIONS THE OUTPUT CARRIES
  * a 4-char code can name genuinely different monuments across eras (rebuilt,
    renamed, reused). Sites whose spread exceeds --ambiguous-m are reported as
    ambiguous rather than averaged into a fictitious point between two real
    monuments.
  * `nearest_other_m` is the distance to the next site in the catalog. Where
    that is below the eventual match radius, no header match can separate the
    two, and stage 3 needs to know that in advance rather than discover it by
    producing confident wrong answers.
  * not every code is a 4-letter site: `02G1`, `0194`, `1824` are campaign point
    numbers, and they are exactly the monuments that are otherwise uncatalogued.

Designed for re-run and merge: pass more roots, get a wider catalog.

Usage:
    scripts/build_crd_catalog.py --root /srv/gnss-archive --root "$P" \
        -o docs/bern52/crd_catalog.csv
    scripts/build_crd_catalog.py --root DIR --want-list sites.txt
"""
from __future__ import annotations

import argparse
import collections
import csv
import math
import re
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

# Fixed-column layout, 0-based slices. Verified against every variant found:
# modern BSW 5.4 (DOMES present, 5 decimals, trailing SYSTEM), legacy ITRF2005
# (no DOMES, 4 decimals), and 1990s GAMIT-era WGS-84 (no EPOCH line, CRLF).
#
# Parsing by whitespace is WRONG here: the station-name field contains a space
# when a DOMES number is present ("ABMF 97103M001"), which shifts every
# subsequent field, and a single file can mix both forms row by row.
COL_NUM = slice(0, 5)
COL_NAME = slice(5, 21)
COL_X = slice(21, 36)
COL_Y = slice(36, 51)
COL_Z = slice(51, 66)
COL_FLAG = slice(66, None)

# A point on or near the Earth's surface. One check that catches column-offset
# bugs, truncated lines and junk rows together, and cheaper than trusting the
# format. Rejects are counted and reported, never dropped silently.
R_MIN, R_MAX = 6_353_000.0, 6_390_000.0

# Strongest solution type wins when a site appears in many files. The point of
# this column is to let a consumer tell a millimetre row from a metre one, so
# anything that is not a recognised solution type collapses to OTHER rather
# than leaking a file title (ITRF2014_0, TQB,96072, CCB00098) into the field
# and making it meaningless.
#
# REFERENCE covers published frame realisations (IGS20, ITRF2014, SLRF2008,
# IGB08 coordinate lists). Those are authoritative coordinates, not a solution
# we computed, and they rank alongside GPSEST.
# Ranks are UNIQUE on purpose. GPSEST and REFERENCE were both 4, which made
# `max()` break the tie by set-iteration order -- and that varies between
# processes, so the committed CSV churned run-to-run with no input change.
# A regenerable artifact that does not regenerate identically is not diffable,
# which was the whole reason for committing it.
#
# REFERENCE sits just below GPSEST: a published frame realisation is
# authoritative for a global station, but where we have our own least-squares
# solution for a site, that is the one this catalog should name.
KIND_RANK = {"RNX2SNX": 6, "GPSEST": 5, "REFERENCE": 4, "COORDINATE": 3,
             "RXOBV3": 2, "CODSPP": 1, "OTHER": 0}
_FRAME_TITLE = re.compile(r"^(ITRF|IGS|IGB|SLRF|ETRF)[0-9_]", re.I)

_HDR_ROW = re.compile(r"^\s*NUM\s+STATION\s+NAME", re.I)
_DATUM = re.compile(r"LOCAL\s+GEODETIC\s+DATUM:\s*(\S+(?:\s*-\s*\S+)?)", re.I)
_EPOCH = re.compile(r"EPOCH:\s*(\d{4}-\d{2}-\d{2})")
_DOMES = re.compile(r"^\d{5}[A-Z]\d{3}$")

# First-line tokens that name a column rather than a station.
_WANT_HEADERS = {"SITE", "STATION", "STATION_CODE", "CODE", "NAME", "SITE_CODE"}

A_WGS84 = 6378137.0
F_WGS84 = 1.0 / 298.257223563


@dataclass
class Row:
    site: str
    domes: str
    x: float
    y: float
    z: float
    flag: str
    kind: str
    frame: str
    epoch: str
    source: Path


def classify(first_line: str) -> str:
    """The program that produced the file, which sets how good the numbers are."""
    tok = first_line.strip().split()[0] if first_line.strip() else ""
    tok = tok.rstrip(":")
    if tok.startswith("RNX2SNX"):
        return "RNX2SNX"
    if _FRAME_TITLE.match(tok):
        return "REFERENCE"
    up = tok.upper()
    return up if up in KIND_RANK and up != "OTHER" else "OTHER"


def parse_crd(path: Path) -> tuple[list[Row], int]:
    """Return (rows, rejects). Never raises on a malformed file.

    `rejects` is a Counter keyed by reason, not a bare total. A count alone
    cannot distinguish 2,700 rows of genuine junk from 2,700 rows lost to one
    systematic parsing fault -- both look like 0.5%. The reasons separate them.
    """
    try:
        text = path.read_text(encoding="ascii", errors="replace")
    except OSError:
        return [], collections.Counter(), {}
    lines = text.splitlines()          # handles CRLF; the 1990s files use it
    if not lines:
        return [], collections.Counter(), {}

    kind = classify(lines[0])
    head = "\n".join(lines[:6])
    m = _DATUM.search(head)
    frame = re.sub(r"\s*-\s*", "-", m.group(1)).strip() if m else ""
    m = _EPOCH.search(head)            # absent in the oldest variant
    epoch = m.group(1) if m else ""

    start = None
    for i, line in enumerate(lines):
        if _HDR_ROW.match(line):
            start = i + 1
            break
    if start is None:
        return [], collections.Counter(), {}

    rows: list[Row] = []
    rejects: collections.Counter[str] = collections.Counter()
    samples: dict[str, str] = {}
    for line in lines[start:]:
        if len(line) < 66 or not line[COL_NUM].strip().isdigit():
            continue
        name = line[COL_NAME].strip()
        if not name:
            continue
        try:
            x = float(line[COL_X])
            y = float(line[COL_Y])
            z = float(line[COL_Z])
        except ValueError:
            rejects["non-numeric coordinate field"] += 1
            samples.setdefault("non-numeric coordinate field", line[:78])
            continue
        radius = math.sqrt(x * x + y * y + z * z)
        if not (R_MIN <= radius <= R_MAX):
            # Separated because they mean different things: an all-zero row is
            # a placeholder or a LEO entry the file never filled in, whereas a
            # plausible-but-wrong radius is a solution that genuinely failed.
            # Only the second is evidence about the data.
            if radius < 1000.0:
                reason = "placeholder / LEO (radius ~0)"
            elif radius < R_MIN:
                reason = "radius below Earth surface (failed solution)"
            else:
                reason = "radius above Earth surface (failed solution)"
            rejects[reason] += 1
            samples.setdefault(reason, f"{line[:60]}  r={radius:,.0f} m")
            continue
        parts = name.split()
        site = parts[0].upper()
        domes = parts[1] if len(parts) > 1 and _DOMES.match(parts[1].upper()) else ""
        rows.append(Row(site, domes, x, y, z, line[COL_FLAG].strip(),
                        kind, frame, epoch, path))
    return rows, rejects, samples


def cluster_rows(rows: list[Row], radius: float) -> list[list[Row]]:
    """Group positions so that one site code naming several monuments is not
    silently averaged into one point between them.

    Leader clustering, not single-linkage: each row is compared against the
    first member of each cluster, not every member, so clusters cannot chain
    across a corridor of intermediate points. At a 1 km radius against real
    monuments that difference does not arise, and the cheaper rule keeps the
    published coordinate anchored to one physical point.
    """
    clusters: list[list[Row]] = []
    for r in rows:
        p = (r.x, r.y, r.z)
        for c in clusters:
            if math.dist(p, (c[0].x, c[0].y, c[0].z)) <= radius:
                c.append(r)
                break
        else:
            clusters.append([r])
    return clusters


def to_geodetic(x: float, y: float, z: float) -> tuple[float, float, float]:
    """ECEF -> lat, lon (degrees), ellipsoidal height (m). WGS-84; the frame
    differences this ignores are far below the resolution that matters."""
    e2 = 2 * F_WGS84 - F_WGS84 ** 2
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1 - e2))
    for _ in range(6):
        n = A_WGS84 / math.sqrt(1 - e2 * math.sin(lat) ** 2)
        h = p / math.cos(lat) - n
        lat = math.atan2(z, p * (1 - e2 * n / (n + h)))
    n = A_WGS84 / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    h = p / math.cos(lat) - n
    return math.degrees(lat), math.degrees(lon), h


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", type=Path, action="append", required=True,
                    help="directory to walk; repeatable, and re-running with "
                         "more roots extends the catalog")
    ap.add_argument("-o", "--output", type=Path,
                    default=Path("docs/bern52/crd_catalog.csv"))
    ap.add_argument("--want-list", type=Path,
                    help="file of site codes, one per line or first CSV column; "
                         "coverage against it is reported")
    ap.add_argument("--ambiguous-m", type=float, default=1000.0,
                    help="spread above which a code is reported as naming more "
                         "than one monument (default 1000)")
    args = ap.parse_args()

    files = sorted({p for r in args.root for p in r.rglob("*")
                    if p.is_file() and p.suffix.lower() == ".crd"})
    print(f"  CRD files found: {len(files)}")

    by_site: dict[str, list[Row]] = defaultdict(list)
    rejects: collections.Counter[str] = collections.Counter()
    reject_files: collections.Counter[str] = collections.Counter()
    samples: dict[str, str] = {}
    wholly_rejected: list[Path] = []
    n_parsed = no_header = 0
    for f in files:
        rows, rej, samp = parse_crd(f)
        rejects.update(rej)
        if rej:
            reject_files[str(f)] = sum(rej.values())
            # A file where EVERY row fails is a different animal from one with
            # a few bad rows: it is a solution that diverged wholesale, not
            # scattered junk. FN142881.CRD is one -- all 52 stations sit ~600 km
            # off at 491 km altitude, from a GPSEST run that did not converge.
            if not rows:
                wholly_rejected.append(f)
        for k, v in samp.items():
            samples.setdefault(k, v)
        if not rows and not rej:
            no_header += 1
        for r in rows:
            by_site[r.site].append(r)
            n_parsed += 1

    total_rej = sum(rejects.values())
    print(f"  rows parsed: {n_parsed}   rejected: {total_rej}"
          f"   files with no coordinate block: {no_header}")
    for reason, n in rejects.most_common():
        print(f"    {n:>6}  {reason}")
        print(f"            e.g. {samples.get(reason, '')}")
    # A systematic fault concentrates in a few files; genuine junk spreads out.
    if reject_files:
        top = reject_files.most_common(3)
        print(f"    rejects spread over {len(reject_files)} files; "
              f"worst: " + ", ".join(
                  f"{Path(f).parent.name}/{Path(f).name}({n})" for f, n in top))
        # The number that separates "genuine junk, diffuse" from "one
        # systematic fault": a parser bug would reject whole files uniformly.
        print(f"    files rejected ENTIRELY (diverged solutions, not parse "
              f"failures): {len(wholly_rejected)}")
        for w in wholly_rejected[:3]:
            print(f"      {w.parent.name}/{w.name}")
    print(f"  distinct site codes: {len(by_site)}")

    # Median, not mean: one bad CODSPP fix drags a mean; the median across
    # dozens of files ignores it.
    #
    # But a median is only meaningful if the rows describe ONE monument. CATA
    # is three: two Philippine sites ~220 km apart plus an Argentine station
    # that appears in a global ITRF reference file. Its global median lands in
    # empty ocean between them -- a confident, fictitious point of exactly the
    # kind this catalog exists to avoid producing.
    #
    # So: cluster first, publish the LARGEST cluster, and flag the site. The
    # coordinate is then at least a real monument, and `ambiguous` plus
    # `n_clusters` say not to trust it blindly.
    cat = {}
    for site, rows in by_site.items():
        clusters = cluster_rows(rows, args.ambiguous_m)
        clusters.sort(key=len, reverse=True)
        main = clusters[0]
        mx = statistics.median(r.x for r in main)
        my = statistics.median(r.y for r in main)
        mz = statistics.median(r.z for r in main)
        # Spread within the published cluster, and the full extent across all
        # of them -- two different questions, both worth answering.
        spread = max(math.dist((r.x, r.y, r.z), (mx, my, mz)) for r in main)
        all_spread = max(math.dist((r.x, r.y, r.z), (mx, my, mz)) for r in rows)
        rows = main
        lat, lon, h = to_geodetic(mx, my, mz)
        kinds = {r.kind for r in rows}
        # (rank, name) so an unranked kind still resolves deterministically.
        best = max(kinds, key=lambda k: (KIND_RANK.get(k, 0), k))
        eps = sorted({r.epoch for r in rows if r.epoch})
        cat[site] = {
            "site": site,
            "domes": next((r.domes for r in rows if r.domes), ""),
            "x": f"{mx:.4f}", "y": f"{my:.4f}", "z": f"{mz:.4f}",
            "lat": f"{lat:.7f}", "lon": f"{lon:.7f}", "height": f"{h:.3f}",
            "n_files": len({r.source for r in rows}),
            "spread_m": f"{spread:.2f}",
            "n_clusters": len(clusters),
            "ambiguous": "yes" if len(clusters) > 1 else "",
            "cluster_extent_m": f"{all_spread:.1f}" if len(clusters) > 1 else "",
            "frames": "|".join(sorted({r.frame for r in rows if r.frame})),
            "epoch_min": eps[0] if eps else "",
            "epoch_max": eps[-1] if eps else "",
            "best_kind": best,
            "_xyz": (mx, my, mz),
        }

    # Nearest other site: where this is below the eventual match radius, no
    # header match can separate the pair.
    sites = list(cat)
    for a in sites:
        xa = cat[a]["_xyz"]
        best_d, best_s = None, ""
        for b in sites:
            if b == a:
                continue
            d = math.dist(xa, cat[b]["_xyz"])
            if best_d is None or d < best_d:
                best_d, best_s = d, b
        cat[a]["nearest_other_site"] = best_s
        cat[a]["nearest_other_m"] = f"{best_d:.1f}" if best_d is not None else ""

    cols = ["site", "domes", "x", "y", "z", "lat", "lon", "height", "n_files",
            "spread_m", "ambiguous", "n_clusters", "cluster_extent_m",
            "frames", "epoch_min", "epoch_max", "best_kind",
            "nearest_other_site", "nearest_other_m"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as fh:
        fh.write("# Bernese CRD site-code index -- an IDENTIFICATION index, not a\n"
                 "# coordinate product. Frames and epochs are NOT harmonised; rows\n"
                 "# derived from CODSPP are metre-level. See build_crd_catalog.py.\n")
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for s in sorted(cat):
            w.writerow(cat[s])
    print(f"  wrote {args.output}  ({len(cat)} sites)")

    amb = sorted((s for s in cat if cat[s]["ambiguous"]),
                 key=lambda s: -float(cat[s]["cluster_extent_m"]))
    print(f"\n  AMBIGUOUS -- one code, more than one monument "
          f"(clusters > {args.ambiguous_m:g} m apart): {len(amb)}")
    print("    the published row is the LARGEST cluster, not an average")
    for s in amb[:15]:
        print(f"    {s}  {cat[s]['n_clusters']} clusters, extent "
              f"{float(cat[s]['cluster_extent_m']):>12,.0f} m  "
              f"n_files {cat[s]['n_files']}")

    close = sorted((s for s in cat if cat[s]["nearest_other_m"]
                    and float(cat[s]["nearest_other_m"]) < 100),
                   key=lambda s: float(cat[s]["nearest_other_m"]))
    print(f"\n  PAIRS CLOSER THAN 100 m (unseparable by header match): {len(close)}")
    for s in close[:10]:
        print(f"    {s} <-> {cat[s]['nearest_other_site']}  "
              f"{float(cat[s]['nearest_other_m']):.1f} m")

    if args.want_list:
        want = []
        for n, line in enumerate(args.want_list.read_text(errors="replace").splitlines()):
            tok = line.split(",")[0].strip().strip('"').upper()
            # A header only counts as a header on the first line. `SITE` is four
            # characters, exactly like a site code, so nothing about its shape
            # gives it away -- and `docs/bern52/gnss_want_list.csv`, the file
            # most likely to be passed here, leads with it. Left unhandled it
            # inflates the denominator and reports SITE as a missing station.
            if n == 0 and tok in _WANT_HEADERS:
                continue
            if tok and not tok.startswith("#"):
                want.append(tok)
        want = sorted(set(want))
        have = [s for s in want if s in cat]
        print(f"\n  WANT-LIST COVERAGE: {len(have)} / {len(want)}")
        missing = [s for s in want if s not in cat]
        if missing:
            print(f"    missing ({len(missing)}): {' '.join(missing[:30])}"
                  + (" ..." if len(missing) > 30 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
