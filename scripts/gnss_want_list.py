#!/usr/bin/env python3
"""
What GNSS data is still missing — the want-list, from the BERN52 inventory.

WHY THIS EXISTS
---------------
Cass has been asking for missing site RINEX and raw receiver files for years.
The answer to "which ones?" has been in the BERN52 processing inventory the
whole time, encoded as **cell fill colour** rather than text — which is why it
was never greppable and never turned into a list anyone could work from.

`scripts/bern52_inventory_to_csv.py` made it machine-readable. This turns it
into something you can take to a drive bay and tick off.

**955 rows across 271 sites, 1994-2019.** Without this, searching a disk for
"GNSS files" matches thousands of files and tells you nothing about whether
you are done. With it, a scan becomes a diff against a finite list.

USAGE
    python3 scripts/gnss_want_list.py                  # write the outputs
    python3 scripts/gnss_want_list.py --sites          # bare site codes, one per line
    python3 scripts/gnss_want_list.py --grep           # a regex alternation for grep -E
    python3 scripts/gnss_want_list.py --site PALA      # what is missing for one site

`--sites` and `--grep` print to stdout and write nothing, so they can be piped
straight into a scan:

    python3 scripts/gnss_want_list.py --grep | xargs -I{} grep -rlE {} /mnt/bay1

WHAT "MISSING" MEANS HERE, PRECISELY
------------------------------------
A row tagged `Data to be retrieved` in the inventory. That is the surveyors'
own judgement recorded at the time, not an inference from the datapool — so it
includes data that was never collected as well as data collected and mislaid.
Both are worth knowing about; only the second is findable on a drive.

Cross-checking against what is actually on disk is a separate step, and
`rinex-completeness` is the tool for it. This answers "what did we say was
missing", not "what is absent from the datapool today".
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / "docs" / "bern52" / "bern52_inventory.csv"
OUT_CSV = REPO / "docs" / "bern52" / "gnss_want_list.csv"
OUT_MD = REPO / "docs" / "bern52" / "gnss_want_list.md"

WANTED = "Data to be retrieved"


def load_wanted() -> list[dict]:
    if not SOURCE.exists():
        sys.exit(
            f"{SOURCE.relative_to(REPO)} not found. Regenerate it first:\n"
            "  uv run --with openpyxl python scripts/bern52_inventory_to_csv.py"
        )
    with SOURCE.open(encoding="utf-8", newline="") as fh:
        return [r for r in csv.DictReader(fh) if r.get("colour_meaning") == WANTED]


def compress_years(years: list[int]) -> str:
    """``[2010,2011,2012,2015]`` -> ``'2010-2012, 2015'``.

    A site with fifteen scattered years is unreadable as a comma list, and the
    ranges are what tell you which era of media to look on -- pre-2005 is a
    different physical format from 2015.
    """
    if not years:
        return ""
    ys = sorted(set(years))
    out, start, prev = [], ys[0], ys[0]
    for y in ys[1:]:
        if y == prev + 1:
            prev = y
            continue
        out.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = y
    out.append(str(start) if start == prev else f"{start}-{prev}")
    return ", ".join(out)


def by_site(rows: list[dict]) -> dict[str, dict]:
    acc: dict[str, dict] = defaultdict(
        lambda: {"years": [], "sheets": set(), "remarks": set()}
    )
    for r in rows:
        site = (r.get("site") or "").strip().upper()
        if not site:
            continue
        entry = acc[site]
        year = (r.get("year") or "").strip()
        if year.isdigit():
            entry["years"].append(int(year))
        if r.get("sheet"):
            entry["sheets"].add(r["sheet"])
        # "False" is openpyxl's rendering of an unticked checkbox cell, not a
        # remark. Dropping it here keeps the field notes readable.
        for key in ("remarks", "status"):
            v = (r.get(key) or "").strip()
            if v and v.lower() not in {"false", "true", "none"}:
                entry["remarks"].add(v)
    return acc


def write_outputs(rows: list[dict]) -> None:
    sites = by_site(rows)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["site", "year", "sheet", "remarks"])
        for r in sorted(
            rows, key=lambda r: ((r.get("site") or "").upper(), r.get("year") or "")
        ):
            remark = (r.get("remarks") or "").strip()
            w.writerow(
                [
                    (r.get("site") or "").strip().upper(),
                    (r.get("year") or "").strip(),
                    r.get("sheet", ""),
                    "" if remark.lower() in {"false", "true", "none"} else remark,
                ]
            )

    campaign = sum(1 for r in rows if r.get("sheet") == "Campaign")
    continuous = len(rows) - campaign
    ranked = sorted(sites.items(), key=lambda kv: (-len(kv[1]["years"]), kv[0]))

    md: list[str] = []
    md.append("# GNSS want-list — what the inventory says is still missing\n")
    md.append(
        f"**{len(rows)} site-years across {len(sites)} sites.** "
        f"Campaign {campaign}, continuous {continuous}.\n"
    )
    md.append(
        "Generated from `bern52_inventory.csv`, where these are cells whose "
        "**fill colour** means *Data to be retrieved* — the surveyors' own "
        "judgement recorded at the time. Regenerate with:\n\n"
        "```bash\npython3 scripts/gnss_want_list.py\n```\n"
    )
    md.append(
        "> **What this is not.** It records what was *said* to be missing, not "
        "what is absent from the datapool today. Some of it was never "
        "collected and will not be on any drive. Cross-check against what is "
        "actually on disk with `rinex-completeness`.\n"
    )
    # Rows whose colour says "to be retrieved" while their own text note says
    # the opposite. Check these first: they may already be in hand, and the
    # colour simply never got updated when the data arrived.
    DONE_WORDS = {"complete", "data complete", "finished", "done"}
    contradictory = sorted(
        {
            site
            for site, e in sites.items()
            if any(r.strip().lower() in DONE_WORDS for r in e["remarks"])
        }
    )
    if contradictory:
        md.append("\n## Check these first — the colour and the note disagree\n")
        md.append(
            f"**{len(contradictory)} sites** are filled *Data to be retrieved* while "
            "carrying a text note saying the opposite (`Complete`, `Finished`, "
            "`Data complete`).\n\n"
            "Either the data arrived and the fill was never updated, or the note "
            "is aspirational. **The first case costs nothing to confirm and "
            "shrinks the list**, so start here rather than at the top of the "
            "ranking below.\n"
        )
        md.append("| site | years | note |")
        md.append("|---|---|---|")
        for site in contradictory:
            e = sites[site]
            md.append(
                f"| `{site}` | {compress_years(e['years'])} | "
                f"{'; '.join(sorted(e['remarks']))} |"
            )

    md.append("\n## Sites, most-missing first\n")
    md.append("| site | site-years | years | sheet | field notes |")
    md.append("|---|---:|---|---|---|")
    for site, e in ranked:
        notes = "; ".join(sorted(e["remarks"]))[:80]
        md.append(
            f"| `{site}` | {len(e['years'])} | {compress_years(e['years'])} | "
            f"{', '.join(sorted(e['sheets']))} | {notes} |"
        )
    md.append(
        "\n## Scanning against this\n\n"
        "```bash\n"
        "# every site code, one per line\n"
        "python3 scripts/gnss_want_list.py --sites\n\n"
        "# as a regex, for a single pass over a mounted bay\n"
        "python3 scripts/gnss_want_list.py --grep\n\n"
        "# then, per drive\n"
        "uv run drive-arch scan /mnt/bay1\n"
        "```\n\n"
        "**Mount anything from the Backup Plus era read-only.** That drive "
        "corrupts fresh writes and is retired read-only — see `SETTLED.md`.\n"
    )
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"{len(rows)} site-years, {len(sites)} sites")
    print(f"  -> {OUT_CSV.relative_to(REPO)}")
    print(f"  -> {OUT_MD.relative_to(REPO)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sites", action="store_true", help="Print site codes, one per line.")
    ap.add_argument("--grep", action="store_true", help="Print a regex alternation.")
    ap.add_argument("--site", metavar="CODE", help="Show what is missing for one site.")
    args = ap.parse_args()

    rows = load_wanted()
    sites = by_site(rows)

    if args.sites:
        print("\n".join(sorted(sites)))
        return 0
    if args.grep:
        print("(" + "|".join(sorted(sites)) + ")")
        return 0
    if args.site:
        code = args.site.strip().upper()
        e = sites.get(code)
        if e is None:
            print(f"{code}: nothing outstanding in the inventory")
            return 1
        print(f"{code}: {len(e['years'])} site-years — {compress_years(e['years'])}")
        for r in sorted(e["remarks"]):
            print(f"  note: {r}")
        return 0

    write_outputs(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
