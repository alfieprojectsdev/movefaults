"""Station files (stage 4, read-only): where each station is listed in the eight files.

The file names come from the campaign's PCF (V_STAINF, V_CRDINF, V_BLQINF,
V_ATLINF, in V_REFDIR), as the BPE reads them. Adding a site and using a final
CRD as a priori are reviewed changes for later; nothing here writes.
"""

from __future__ import annotations

import re
from pathlib import Path

from bernese_workflow.run_plan import expand_bsw_path, pcf_variable

from .settings import Campaign, Settings
from .status import _pcf_text

FILES = ["STA", "CRD", "ABB", "ATL", "PLD", "VEL", "CLU", "BLQ"]
_VAR = {"STA": "V_STAINF", "BLQ": "V_BLQINF", "ATL": "V_ATLINF"}  # the rest: V_CRDINF
_CODE = re.compile(r"^[A-Z0-9]{4}$")


def _first_code(tokens: list[str]) -> str | None:
    return tokens[0] if tokens and _CODE.match(tokens[0]) and not tokens[0].isdigit() else None


def stations_in(ext: str, text: str) -> dict[str, set[str]]:
    """Station code -> the full names listed under it (BILI 12363M001, BILI BILI)."""
    out: dict[str, set[str]] = {}

    def add(tokens: list[str]) -> None:
        code = _first_code(tokens)
        if code:
            out.setdefault(code, set()).add(" ".join(tokens[:2]) if len(tokens) > 1 else code)

    lines = text.splitlines()
    if ext in ("CRD", "VEL", "PLD"):
        for line in lines[4:]:
            t = line.split()
            if len(t) > 2 and t[0].isdigit():
                add(t[1:])
    elif ext in ("ABB", "CLU"):
        for line in lines[4:]:
            if line.startswith("*"):
                continue
            add(line.split())
    elif ext == "STA":
        on = False
        for line in lines:
            if line.startswith("TYPE 001"):
                on = True
                continue
            if line.startswith("TYPE 002"):
                break
            if on and line[:1].isalnum() and not line.startswith("STATION"):
                add(line.split())
    elif ext in ("ATL", "BLQ"):
        for line in lines:
            if line.startswith("$$"):
                if "END TABLE" in line:
                    break
                continue
            t = line.split()
            if t and not re.match(r"^[-+.\d]", t[0]):
                add(t)
    return out


def refdir_of(s: Settings, c: Campaign, year: int) -> str:
    text = _pcf_text(s, c.pcf) or ""
    return expand_bsw_path(pcf_variable(text, "V_REFDIR") or "", s.env, year) or str(
        s.datapool / "REF54"
    )


def campaign_files(s: Settings, c: Campaign, year: int) -> dict[str, Path]:
    """The eight station files the campaign's PCF names, as the BPE reads them."""
    text = _pcf_text(s, c.pcf) or ""
    refdir = Path(refdir_of(s, c, year))
    crd = pcf_variable(text, "V_CRDINF") or c.name
    return {
        ext: refdir / f"{pcf_variable(text, _VAR.get(ext, 'V_CRDINF')) or crd}.{ext}"
        for ext in FILES
    }


def coverage(s: Settings, c: Campaign, year: int) -> dict:
    refdir = refdir_of(s, c, year)
    found: dict[str, dict[str, set[str]]] = {}
    files = {}
    for ext, p in campaign_files(s, c, year).items():
        files[ext] = {"name": p.name, "present": p.is_file()}
        found[ext] = stations_in(ext, p.read_text(errors="replace")) if p.is_file() else {}
    codes = sorted(set().union(*[set(v) for v in found.values()]))
    rows = []
    for code in codes:
        cells = {}
        notes = []
        for ext in FILES:
            names = found[ext].get(code, set())
            cells[ext] = len(names)
            if len(names) > 1:
                notes.append(
                    f"{ext}: {len(names)} names share the code ({', '.join(sorted(names))})"
                )
        if code in found["STA"] and not cells["BLQ"]:
            notes.append("Not in the BLQ: ocean loading would fail (GTOCNL).")
        rows.append({"station": code, "cells": cells, "notes": notes})
    return {"campaign": c.name, "refdir": refdir, "files": files, "columns": FILES, "rows": rows}
