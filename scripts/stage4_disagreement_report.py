#!/usr/bin/env python3
"""Stage 4 — turn the stage-3 matches into a reviewable disagreement report.

Stage 3 attributed 443,199 RINEX files to monuments by header position, and
recorded what the filename, the RINEX marker and the directory path each
claimed. Where those disagree, one of them is wrong. This groups the
disagreements so a person can decide which, instead of reading 443,199 rows.

WHAT A DISAGREEMENT IS AND IS NOT
It is NOT an error to be corrected automatically. Three sources of evidence
exist and none is authoritative:

  * the header position -- measured, but a single-point fix worth ~100 m, and a
    cold start can be kilometres out
  * the filename and marker -- what somebody typed, at the time
  * the directory -- inference from how somebody once filed a folder

A conflict says two of them differ. It does not say which to believe. The
catalog entry itself could be the error: `PHIV` is in the catalog and appears
to be an institution name rather than a monument.

WHY GROUPING IS THE WHOLE JOB
735 filename conflicts and 1,017 path conflicts are unreadable as rows and
obvious as groups. `Obsfiles/masb/1991/033/` holding masf, mash and masc files
is one fact about one directory, not 99 separate findings. The report is
ordered by how many files each pattern explains, so the largest cause is read
first.

DECIDABILITY
Each group carries the evidence needed to settle it:
  * how far the header is from the site the name claims (`claimed_m`) --
    a conflict where the claimed site is 240 m away is a different thing from
    one where it is 1,062 km away
  * whether filename and marker agree with each other, which is the difference
    between one typo and a systematically mislabelled directory

Usage:
    scripts/stage4_disagreement_report.py --matches ~/stage3-output/matches_all.csv
    scripts/stage4_disagreement_report.py --matches M.csv -o docs/bern52/stage4.md
"""
from __future__ import annotations

import argparse
import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", errors="replace") as fh:
        return list(csv.DictReader(ln for ln in fh if not ln.startswith("#")))


def fmt_m(v: float) -> str:
    return f"{v / 1000:,.0f} km" if v >= 1000 else f"{v:,.0f} m"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--matches", type=Path, required=True)
    ap.add_argument("-o", "--output", type=Path,
                    default=Path("docs/bern52/stage4_disagreements.md"))
    ap.add_argument("--catalog", type=Path,
                    default=Path("docs/bern52/crd_catalog.csv"),
                    help="used to separate catalog ambiguity from misnamed files")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    rows = load(args.matches)
    if not rows:
        print(f"FATAL: no rows in {args.matches}", file=sys.stderr)
        return 1
    print(f"  rows: {len(rows):,}")

    # A code the catalog marks AMBIGUOUS names more than one monument. When a
    # file claims such a code and the position matches a different one, that is
    # the catalog's limitation, not evidence the file is misnamed: the
    # published row is one cluster and the file came from another. Without this
    # split the largest "conflict" -- 213 files claiming MALA, which has four
    # clusters 10,373 km apart -- reads as 213 mislabelled files.
    amb, clusters = set(), {}
    if args.catalog.is_file():
        with args.catalog.open(encoding="utf-8") as fh:
            for c in csv.DictReader(ln for ln in fh if not ln.startswith("#")):
                if c.get("ambiguous"):
                    amb.add(c["site"])
                    clusters[c["site"]] = c.get("n_clusters", "")
    print(f"  catalog codes flagged ambiguous: {len(amb)}")

    name_conf = [r for r in rows if r.get("agrees") == "NO"]
    path_conf = [r for r in rows if r.get("path_agrees") == "NO"]
    print(f"  filename conflicts: {len(name_conf)}   path conflicts: {len(path_conf)}")

    # Group by the PATTERN, not the file. One mislabelled directory is one
    # finding regardless of how many files it holds.
    def group(conf, claim_field):
        g = defaultdict(list)
        for r in conf:
            g[(r["matched_site"], r[claim_field])].append(r)
        return sorted(g.items(), key=lambda kv: -len(kv[1]))

    name_groups = group(name_conf, "name_site")
    path_groups = group(path_conf, "path_site")

    # A directory that holds files matching MANY different sites is a shared
    # campaign folder, which is a different diagnosis from one that is simply
    # mislabelled -- and the fix differs too.
    dirs = defaultdict(set)
    for r in path_conf:
        dirs[str(Path(r["path"]).parent)].add(r["matched_site"])
    multi = sorted(((d, s) for d, s in dirs.items() if len(s) > 1),
                   key=lambda kv: -len(kv[1]))

    out = []
    A = out.append
    A("# Stage 4 — disagreement report\n")
    A("Generated by `scripts/stage4_disagreement_report.py` from the stage-3\n"
      "matches. Grouped by pattern, ordered by how many files each explains.\n")
    A("**A disagreement is not an error to correct automatically.** Three\n"
      "sources of evidence exist — the header position (measured, ~100 m), the\n"
      "filename and marker (what somebody typed), and the directory (inference\n"
      "from how somebody once filed a folder). A conflict says two differ; it\n"
      "does not say which to believe. The catalog entry itself may be wrong.\n")

    A(f"\n## Scale\n\n| | files |\n|---|---:|\n"
      f"| rows examined | {len(rows):,} |\n"
      f"| filename/marker conflicts | {len(name_conf):,} |\n"
      f"| directory-path conflicts | {len(path_conf):,} |\n"
      f"| distinct filename patterns | {len(name_groups)} |\n"
      f"| distinct path patterns | {len(path_groups)} |\n")
    A(f"\n{len(name_conf):,} filename conflicts reduce to **{len(name_groups)} "
      f"patterns**, and {len(path_conf):,} path conflicts to "
      f"**{len(path_groups)}**. That ratio is why this stage exists.\n")

    A("\n## Filename and marker conflicts\n")
    A("`claimed_m` is the distance from the header to the site the *filename*\n"
      "claims. It is what makes a conflict decidable: a claimed site 240 m away\n"
      "is inside what a header can be wrong by; one 1,000 km away is not.\n")
    amb_groups = [(k, g) for k, g in name_groups if k[1] in amb]
    clean_groups = [(k, g) for k, g in name_groups if k[1] not in amb]
    n_amb = sum(len(g) for _, g in amb_groups)
    n_clean = sum(len(g) for _, g in clean_groups)

    A(f"\n### Split first: {n_amb} of {len(name_conf)} are catalog ambiguity\n")
    A("A code the catalog marks `ambiguous` names more than one monument, and\n"
      "the published row is only the largest cluster. A file claiming such a\n"
      "code whose position matches a *different* site is not evidence of a\n"
      "misnamed file — it is the catalog being unable to say which monument\n"
      "that code meant.\n")
    A(f"\n**{n_amb} files across {len(amb_groups)} patterns claim an ambiguous "
      f"code.** These need the catalog fixed, not the files.\n")
    A("\n| matched | filename says | clusters | files | header→claimed |")
    A("|---|---|---:|---:|---|")
    for (site, claim), g in amb_groups[:args.top]:
        cd = [float(r["claimed_m"]) for r in g if r["claimed_m"]]
        med = fmt_m(statistics.median(cd)) if cd else "—"
        A(f"| `{site}` | `{claim}` | {clusters.get(claim, '?')} | {len(g)} | {med} |")

    A(f"\n### The remaining {n_clean} claim an unambiguous code\n")
    A("Here the catalog knows exactly one monument for that name, so the file\n"
      "and the position genuinely disagree about where the receiver was.\n")
    A("\n| matched | filename says | files | header→claimed | marker agrees with name |")
    A("|---|---|---:|---|---|")
    for (site, claim), g in clean_groups[:args.top]:
        cd = [float(r["claimed_m"]) for r in g if r["claimed_m"]]
        med = fmt_m(statistics.median(cd)) if cd else "—"
        same = sum(1 for r in g if r["marker_site"] == r["name_site"])
        A(f"| `{site}` | `{claim}` | {len(g)} | {med} | "
          f"{'all' if same == len(g) else f'{same}/{len(g)}'} |")

    allcd = sorted(float(r["claimed_m"]) for r in name_conf if r["claimed_m"])
    if allcd:
        A(f"\nAcross all {len(allcd)} conflicts with a measurable claim: "
          f"minimum **{fmt_m(allcd[0])}**, median **{fmt_m(allcd[len(allcd)//2])}**, "
          f"maximum **{fmt_m(allcd[-1])}**. "
          f"{sum(1 for d in allcd if d < 200)} are within 200 m — i.e. inside "
          "what header imprecision alone could explain.\n")

    A("\n### Where the marker and filename agree with each other\n")
    both = [g for k, g in name_groups
            if all(r["marker_site"] == r["name_site"] for r in g)]
    A(f"{sum(len(g) for g in both)} files in {len(both)} patterns have the "
      "filename and the RINEX marker saying the *same* thing, and both\n"
      "differing from the position. Two independent records agreeing makes a\n"
      "typo unlikely — either the file genuinely came from elsewhere, or the\n"
      "catalog entry for that code is wrong.\n")

    A("\n## Directory-path conflicts\n")
    A("Path attribution is inference from how somebody once filed a folder.\n"
      "This is the first evidence that can contradict it.\n")
    A("\n| matched | directory says | files |")
    A("|---|---|---:|")
    for (site, claim), g in path_groups[:args.top]:
        A(f"| `{site}` | `{claim}` | {len(g)} |")

    A("\n### Directories holding more than one site — the dominant cause\n")
    A(f"{len(multi)} directories contain files matching several different\n"
      "monuments. That is a campaign folder holding reference or fiducial data\n"
      "alongside its own site, not a mislabelled directory, and filing by\n"
      "directory name would mislabel every file in it.\n")
    A("\n| directory | distinct sites |")
    A("|---|---|")
    for d, s in multi[:args.top]:
        short = "/".join(Path(d).parts[-3:])
        A(f"| `…/{short}` | {len(s)} — {' '.join(sorted(s)[:6])}"
          f"{' …' if len(s) > 6 else ''} |")

    A("\n## What to do with this\n")
    A("Nothing here should be applied automatically. In rough priority:\n")
    A("1. **Fix the ambiguous catalog codes first.** They account for the\n"
      "   largest conflict groups and need no per-file decision at all — the\n"
      "   catalog cannot currently say which monument the code meant.")
    A("2. **Then the largest unambiguous filename pattern.**")
    A("3. **Patterns where marker and filename agree** — two records against the\n"
      "   position is the strongest case that the catalog is what needs fixing.")
    A("4. **Multi-site directories** — these do not need per-file decisions;\n"
      "   they need path-derived attribution to stop being trusted for them.")
    A("\n## What this does not establish\n")
    A("* **Not which source is wrong.** Only that they differ.\n"
      "* **Nothing about files with no conflict.** Agreement between a filename\n"
      "  and an imprecise position is weak corroboration, not proof.\n"
      "* **Nothing about the `none` and `ambiguous` verdicts**, which are a\n"
      "  separate question: those files were never attributed at all.\n")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"  wrote {args.output}")
    print(f"  filename patterns: {len(name_groups)}   path patterns: {len(path_groups)}"
          f"   multi-site dirs: {len(multi)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
