#!/usr/bin/env python3
"""
Extract the dislocation-model results compilation into committable form.

WHY THIS EXISTS
---------------
`analysis/07 Dislocation Model/` is ~62 MB of .pptx and .docx. Committing it
would be the wrong trade three ways: it is opaque to `git diff` (every revision
shows as `Bin`), it cannot be grepped headlessly on the R740, and it is bulk
binary in a repository whose value is its readable history.

But its content settled a question two sessions could not — which inversion
methods have actually been applied to Philippine faults, and whether the
published parameters carry uncertainties. That answer has to live in the repo.

So: extract, do not vendor. The workbooks stay where staff edit them; this
produces a CSV and a markdown summary that are diffable, greppable, and
regenerable when the workbooks change.

USAGE
    uv run --with python-docx python scripts/extract_dislocation_results.py
    uv run --with python-docx python scripts/extract_dislocation_results.py --check

`--check` regenerates to a temporary location and diffs against the committed
output, so CI or a reviewer can tell whether the summary still matches the
source. It does not rewrite anything.

DEPENDENCY NOTE
`python-docx` is deliberately NOT added to this repo's dependencies. It is
needed only to regenerate, not to read the output, and the output is what is
committed. Run it with `uv run --with python-docx` as above.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / "analysis" / "07 Dislocation Model" / "Dislocation Model (Compilation of Results).docx"
OUT_CSV = REPO / "docs" / "project_documentation" / "dislocation_model_results.csv"
OUT_MD = REPO / "docs" / "project_documentation" / "dislocation_model_results.md"

# Rows carrying a fault-segment name in the compilation's own headings. The
# emoji are the document's, not ours -- kept so a reader can match them back.
_SEGMENT_RE = re.compile(r"^[\U0001F300-\U0001FAFF⬛⬜]\s*(.+)$")


def _clean(text: str) -> str:
    return " ".join(text.split()).strip()


def read_document(path: Path):
    try:
        from docx import Document
    except ImportError:  # pragma: no cover - dependency is intentionally absent
        sys.exit(
            "python-docx is not installed. This script is run on demand:\n"
            "  uv run --with python-docx python scripts/extract_dislocation_results.py"
        )
    return Document(str(path))


def segment_for_table(doc, table_index: int) -> str:
    """Map a table to the segment heading that precedes it in document order.

    Uses ``Paragraph.text`` rather than ``itertext()`` on the raw element.
    They disagree: this document's headings carry bookmark/field markup that
    makes ``itertext()`` return the heading THREE times --

        itertext: '🟠 PF: Central Luzon🟠 PF: Central Luzon🟠 PF: Central Luzon'
        par.text: '🟠 PF: Central Luzon'

    -- which silently produced tripled segment names in the first run of this
    script. Caught by reading the output rather than by an error.
    """
    from docx.text.paragraph import Paragraph

    body = doc.element.body
    seen_tables = 0
    current = "(methods reference)"
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = _clean(Paragraph(child, doc).text)
            m = _SEGMENT_RE.match(text)
            if m and "Methods" not in text and "Fault segments" not in text:
                current = _clean(m.group(1))
        elif tag == "tbl":
            if seen_tables == table_index:
                return current
            seen_tables += 1
    return current


def extract_rows(doc) -> list[dict]:
    """One row per (segment, run, parameter). Long format survives edits."""
    rows: list[dict] = []
    for ti, table in enumerate(doc.tables):
        if len(table.rows) < 2 or len(table.columns) < 2:
            continue
        header = [_clean(c.text) for c in table.rows[0].cells]
        if header[0].lower() not in {"description", "fault", "method"}:
            continue
        segment = segment_for_table(doc, ti)
        for row in table.rows[1:]:
            cells = [_clean(c.text) for c in row.cells]
            parameter = cells[0]
            if not parameter:
                continue
            for col in range(1, len(cells)):
                value = cells[col]
                if not value:
                    continue
                rows.append(
                    {
                        "segment": segment,
                        "table": ti,
                        "run": header[col] if col < len(header) else f"col{col}",
                        "parameter": parameter,
                        "value": value,
                    }
                )
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["segment", "table", "run", "parameter", "value"])
        w.writeheader()
        # Sorted so regeneration is deterministic -- without this every rerun
        # shows spurious churn and the readable-diff benefit disappears.
        for r in sorted(rows, key=lambda r: (r["segment"], r["table"], r["run"], r["parameter"])):
            w.writerow(r)


def summarise(rows: list[dict]) -> str:
    by_segment: dict[str, dict[str, dict[str, str]]] = {}
    for r in rows:
        by_segment.setdefault(r["segment"], {}).setdefault(r["run"], {})[r["parameter"]] = r["value"]

    methods: dict[str, set[str]] = {}
    for seg, runs in by_segment.items():
        for run, params in runs.items():
            m = params.get("Method")
            if m:
                methods.setdefault(m, set()).add(f"{seg} / {run}")

    out: list[str] = []
    out.append("# Dislocation model results — what has actually been run\n")
    out.append(
        "**Extracted, not vendored.** Source is\n"
        "`analysis/07 Dislocation Model/Dislocation Model (Compilation of Results).docx`\n"
        "(~62 MB of .pptx/.docx in that directory, deliberately not committed —\n"
        "opaque to `git diff`, not greppable on the R740, and bulk binary).\n"
    )
    out.append(
        "Regenerate with:\n\n"
        "```bash\n"
        "uv run --with python-docx python scripts/extract_dislocation_results.py\n"
        "```\n"
    )
    out.append(
        "This file settles a question that two sessions got wrong from the\n"
        "repository alone. See the correction in\n"
        "[`analysis_port_assessment.md`](analysis_port_assessment.md) finding 5.\n"
    )

    out.append("\n## Methods actually applied\n")
    out.append("| method | segments / runs |")
    out.append("|---|---|")
    for m in sorted(methods):
        where = ", ".join(sorted(methods[m])[:6])
        more = f" (+{len(methods[m]) - 6} more)" if len(methods[m]) > 6 else ""
        out.append(f"| `{m}` | {where}{more} |")

    out.append(
        "\n**All three candidate methods are in production use on Philippine data.**\n"
        "The MCMC is not a method awaiting evaluation — it is the newest one\n"
        "applied. Any claim that it has only run on Taiwanese data is wrong and\n"
        "came from reading `06 Ku-en`'s committed example rather than the record.\n"
    )

    out.append("\n## Segments modelled\n")
    out.append("| segment | runs | reference stations | methods |")
    out.append("|---|---|---|---|")
    for seg in sorted(by_segment):
        runs = by_segment[seg]
        refs = sorted({p.get("Reference station", "") for p in runs.values()} - {""})
        ms = sorted({p.get("Method", "") for p in runs.values()} - {""})
        out.append(
            f"| {seg} | {len(runs)} | {', '.join(refs) or '—'} | {'; '.join(ms) or '—'} |"
        )

    out.append("\n## Uncertainties are published\n")
    intervals = [
        (seg, run, k, v)
        for seg, runs in by_segment.items()
        for run, params in runs.items()
        for k, v in params.items()
        if re.search(r"\(\s*[\d.]+\s*-\s*[\d.]+\s*\)", v)
    ]
    out.append(
        f"{len(intervals)} published parameter values carry an explicit interval.\n"
        "So \"which method gives uncertainties\" was never the open question —\n"
        "all of them do, by different routes.\n"
    )
    if intervals:
        out.append("\nExamples:\n")
        for seg, run, k, v in intervals[:8]:
            out.append(f"- **{seg}** / {run} — {k}: `{v}`")

    out.append(
        "\n## What is still open\n"
        "- The `metropolis_log.m` overflow (`exp(a)*exp(b)` rather than\n"
        "  `exp(a+b)`) is a defect in a method that has **already produced\n"
        "  published intervals**. Whether it affected the 900,000-sample runs is\n"
        "  checkable and has not been checked.\n"
        "- `bootstrap_v2.py` hardcodes reference station `VIGN`, which appears in\n"
        "  the table as the reference for the first two Central Luzon runs. The\n"
        "  script is tied to a specific published run rather than parameterised.\n"
    )
    out.append(
        "\n---\n\nFull long-format extraction: "
        "[`dislocation_model_results.csv`](dislocation_model_results.csv)\n"
    )
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="Diff against committed output; do not write.")
    args = ap.parse_args()

    if not SOURCE.exists():
        sys.exit(f"Source not found: {SOURCE}\nThe workbooks are not committed; see the module docstring.")

    doc = read_document(SOURCE)
    rows = extract_rows(doc)
    if not rows:
        sys.exit("Extracted zero rows — the document structure has changed.")
    md = summarise(rows)

    if args.check:
        import io
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=["segment", "table", "run", "parameter", "value"])
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["segment"], r["table"], r["run"], r["parameter"])):
            w.writerow(r)
        # newline="" on read, because csv.DictWriter emits \r\n and
        # Path.read_text() applies universal-newline translation. Without it
        # --check reports STALE immediately after a successful regeneration --
        # which it did, on the first run of this code.
        def _read(path: Path) -> str | None:
            if not path.exists():
                return None
            with path.open(encoding="utf-8", newline="") as fh:
                return fh.read()

        stale = []
        if _read(OUT_CSV) != buf.getvalue():
            stale.append(str(OUT_CSV.relative_to(REPO)))
        if _read(OUT_MD) != md:
            stale.append(str(OUT_MD.relative_to(REPO)))
        if stale:
            print("STALE — regenerate:\n  " + "\n  ".join(stale))
            return 1
        print("up to date")
        return 0

    write_csv(rows, OUT_CSV)
    OUT_MD.write_text(md, encoding="utf-8")
    print(f"{len(rows)} rows -> {OUT_CSV.relative_to(REPO)}")
    print(f"summary   -> {OUT_MD.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
