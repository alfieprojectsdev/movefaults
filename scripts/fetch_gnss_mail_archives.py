#!/usr/bin/env python3
"""Mirror the BSWMAIL and IGSMAIL archives to a LOCAL cache, for diagnosis.

WHY THIS EXISTS
`bpe_orchestration_design.md` argues that the reason BSW expertise stays siloed
between PHIVOLCS, NAMRIA and CAAP is that the diagnostic knowledge is not
anywhere a pipeline can reach at the moment of failure. Two public archives are
the closest existing approximation of that knowledge, and neither is searchable
offline:

  BSWMAIL  429 messages, 1995-2026, AIUB.  Software-side: program aborts,
           release notes, workarounds, panel settings. This is the corpus that
           seeds the error-signature knowledge base.

  IGSMAIL  ~10-15k messages, 1992-2026, IGS.  Data-side: satellite health
           events, antenna model changes, reference frame transitions, station
           discontinuities. This is the corpus for "why did THIS DAY behave
           oddly", which is a different question from "why did this program
           abort" -- and it is exactly the class of question DOY 036's
           wrongly-fixed ambiguities raised.

WHERE IT WRITES, AND WHY NOT THE REPO
Neither AIUB nor IGS state a licence on these pages. Absence of a notice is not
permission, and **this repository is public** -- committing a mirror would be
redistribution of all-rights-reserved material. So the corpus lands OUTSIDE the
repo (default ~/gnss-mail-archive) and is never added to git.

What may be committed is this script, and knowledge-base entries written in our
own words with a citation. Read the source, derive the entry, cite the URL.

POLITENESS
BSWMAIL has no bulk download, so it needs 429 sequential requests. Default
delay is 1.0 s and existing files are skipped, so a re-run costs nothing. IGSMAIL
is 35 bulk files. Do not lower the delay to be clever.

Usage:
    scripts/fetch_gnss_mail_archives.py --source bswmail
    scripts/fetch_gnss_mail_archives.py --source igsmail
    scripts/fetch_gnss_mail_archives.py --source both --out ~/gnss-mail-archive
    scripts/fetch_gnss_mail_archives.py --source bswmail --grep 'DIMENSION TOO SMALL'
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

BSWMAIL_URL = "https://www.aiub.unibe.ch/download/bswmail/bswmail.{n:04d}"
BSWMAIL_MAX = 429  # as indexed 2026-08-29; --max overrides when the list grows
IGSMAIL_URL = "https://lists.igs.org/pipermail/igsmail/{year}.txt"
IGSMAIL_GZ = "https://lists.igs.org/pipermail/igsmail/{year}.txt.gz"
IGSMAIL_FIRST, IGSMAIL_LAST = 1992, 2026
UA = "movefaults-gnss-archive/1.0 (PHIVOLCS geodesy; local research cache)"


def fetch(url: str, timeout: int = 60) -> bytes | None:
    """One GET. Returns None on 404 (expected at the end of a sequence)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"    HTTP {e.code} for {url}", file=sys.stderr)
        return None
    except Exception as e:  # noqa: BLE001 - one bad fetch must not end the mirror
        print(f"    {type(e).__name__} for {url}: {str(e)[:70]}", file=sys.stderr)
        return None


def record(manifest: dict, key: str, url: str, data: bytes, path: Path) -> None:
    manifest[key] = {
        "url": url,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "retrieved": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "path": str(path.name),
    }


def do_bswmail(out: Path, delay: float, limit: int, manifest: dict) -> int:
    d = out / "bswmail"
    d.mkdir(parents=True, exist_ok=True)
    got = skipped = 0
    for n in range(1, limit + 1):
        p = d / f"bswmail.{n:04d}"
        if p.exists() and p.stat().st_size > 0:
            skipped += 1
            continue
        url = BSWMAIL_URL.format(n=n)
        data = fetch(url)
        if data is None:
            # A gap mid-sequence is possible; only stop after several in a row.
            continue
        p.write_bytes(data)
        record(manifest, f"bswmail.{n:04d}", url, data, p)
        got += 1
        if got % 25 == 0:
            print(f"    {got} fetched ({n}/{limit})")
        time.sleep(delay)
    print(f"  bswmail: {got} fetched, {skipped} already present -> {d}")
    return got


def do_igsmail(out: Path, delay: float, manifest: dict) -> int:
    d = out / "igsmail"
    d.mkdir(parents=True, exist_ok=True)
    got = skipped = 0
    for year in range(IGSMAIL_FIRST, IGSMAIL_LAST + 1):
        p = d / f"{year}.txt"
        if p.exists() and p.stat().st_size > 0:
            skipped += 1
            continue
        data = fetch(IGSMAIL_URL.format(year=year))
        url = IGSMAIL_URL.format(year=year)
        if data is None:
            url = IGSMAIL_GZ.format(year=year)
            raw = fetch(url)
            if raw is None:
                continue
            try:
                data = gzip.decompress(raw)
            except OSError:
                print(f"    {year}: not valid gzip, skipped", file=sys.stderr)
                continue
        p.write_bytes(data)
        record(manifest, f"igsmail.{year}", url, data, p)
        got += 1
        print(f"    {year}: {len(data):,} bytes")
        time.sleep(delay)
    print(f"  igsmail: {got} fetched, {skipped} already present -> {d}")
    return got


def do_grep(out: Path, pattern: str) -> int:
    """Search the local cache. This is the point of having it offline."""
    rx = re.compile(pattern, re.I)
    hits = 0
    for p in sorted(out.rglob("*")):
        if not p.is_file() or p.name == "MANIFEST.json":
            continue
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                subj = ""
                for L in text.splitlines()[:40]:
                    if L.lower().startswith("subject:"):
                        subj = L[8:].strip()
                        break
                print(f"  {p.parent.name}/{p.name}:{i}")
                if subj:
                    print(f"      subject: {subj[:88]}")
                print(f"      {line.strip()[:110]}")
                hits += 1
                break
    print(f"\n  {hits} file(s) matched /{pattern}/")
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--source", choices=("bswmail", "igsmail", "both"), default="both")
    ap.add_argument("--out", type=Path, default=Path.home() / "gnss-mail-archive")
    ap.add_argument("--delay", type=float, default=1.0,
                    help="seconds between requests (default 1.0; do not lower)")
    ap.add_argument("--max", type=int, default=BSWMAIL_MAX,
                    help=f"highest bswmail number to try (default {BSWMAIL_MAX})")
    ap.add_argument("--grep", metavar="REGEX",
                    help="search the existing local cache instead of fetching")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    if args.grep:
        return 0 if do_grep(args.out, args.grep) else 1

    mf_path = args.out / "MANIFEST.json"
    manifest = json.loads(mf_path.read_text()) if mf_path.is_file() else {}

    print(f"  cache: {args.out}   delay: {args.delay}s")
    print("  NOTE: no licence is stated by AIUB or IGS. This cache is for local")
    print("        reference only. Do not commit it; this repository is public.")
    if args.source in ("bswmail", "both"):
        do_bswmail(args.out, args.delay, args.max, manifest)
    if args.source in ("igsmail", "both"):
        do_igsmail(args.out, args.delay, manifest)

    mf_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"  manifest: {mf_path} ({len(manifest)} entries with sha256)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
