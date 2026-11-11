"""Station files, the read-only helpers (stage 4): nothing here writes a file.

Three things the work instruction does by hand, prepared and checked here so a
person makes the one change that remains:

onsala_request   the coordinate block to paste into the Chalmers/Onsala ocean
                 loading form, for the stations in the STA with no BLQ block,
                 and the model settings the BLQ was made with (5.3.10)
check_blq_reply  the emailed reply, checked before scripts/merge_blq.py merges
                 it: six rows of 11 values per station, the key line GTOCNL
                 matches on, stations already in the BLQ, model settings that
                 differ from the BLQ's
apriori_preview  a final CRD against the campaign's a priori CRD, per station
                 in north, east and up (5.5.6, "use a final CRD as a priori")

The merge and the a priori replacement themselves stay with the maintainer
until it is decided how a change to a production campaign file is reviewed.
"""

from __future__ import annotations

import math
import re

import pymap3d

from .settings import Campaign, Settings
from .stations import campaign_files, stations_in
from .status import year_dir

# --------------------------------------------------------------------------- CRD


def _float(t: str) -> float | None:
    try:
        return float(t)
    except ValueError:
        return None


def read_crd(text: str) -> dict:
    """Datum, epoch and stations of a Bernese CRD file.

    Each station keyed by its full name ("ABMF 97103M001", or the code alone
    when the file has no second name), with X, Y, Z in metres and the flag
    column ("" for a station carried from the a priori file and not estimated).
    """
    datum = epoch = None
    m = re.search(r"LOCAL GEODETIC DATUM:\s*(\S+)\s+EPOCH:\s*(\S+ \S+)", text)
    if m:
        datum, epoch = m[1], m[2]
    rows: dict[str, dict] = {}
    for line in text.splitlines():
        t = line.split()
        if len(t) < 5 or not t[0].isdigit():
            continue
        if _float(t[2]) is None:  # a second name: DOMES or a repeat of the code
            name, rest = f"{t[1]} {t[2]}", t[3:]
        else:
            name, rest = t[1], t[2:]
        xyz = [_float(v) for v in rest[:3]]
        if len(xyz) < 3 or any(v is None for v in xyz):
            continue
        rows[name] = {"xyz": xyz, "flag": " ".join(rest[3:])}
    return {"datum": datum, "epoch": epoch, "stations": rows}


def to_neu(xyz: list[float], d: list[float]) -> tuple[float, float, float]:
    """A difference ``d`` (dX, dY, dZ) at ``xyz``, as north, east, up (WGS84),
    with pymap3d as crd_pipeline uses it."""
    lat, lon, _ = pymap3d.ecef2geodetic(*xyz, deg=False)
    e, n, u = pymap3d.ecef2enuv(*d, lat, lon, deg=False)
    return n, e, u


# --------------------------------------------------------------------------- BLQ

# The model settings a BLQ header records, as the Onsala service writes them.
_SETTINGS = {
    "ocean tide model": re.compile(r"\$\$\s*Ocean tide model:\s*(\S+)", re.I),
    "centre of mass correction (CMC)": re.compile(r"\$\$\s*CMC:\s*(\S+)", re.I),
    "Green's function": re.compile(r"\$\$\s*(\S+)\s+Green'?s\s+function", re.I),
}


def blq_settings(text: str) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for label, rx in _SETTINGS.items():
        m = rx.search(text)
        out[label] = m[1] if m else None
    return out


_NUM = re.compile(r"^[-+.\d]")


def _name_line(line: str) -> str | None:
    """The code on a station's first line ("  BTNG", "  ABUY   ABUY"), else None.

    The same rule as scripts/merge_blq.py: two leading blanks, one or two tokens,
    the first not a number. Data rows carry 11 numbers; $$ lines are comments.
    """
    if not line.startswith("  ") or line.strip().startswith("$$"):
        return None
    t = line.split()
    if not t or len(t) > 2 or _NUM.match(t[0]):
        return None
    return t[0].upper()


def blq_blocks(text: str) -> list[dict]:
    """Each station block in a BLQ text, in order: its code, its lines, and
    whether it came after ``$$ END TABLE`` (where Bernese never reads)."""
    out: list[dict] = []
    after_end = False
    for line in text.splitlines():
        if "END TABLE" in line and line.strip().startswith("$$"):
            after_end = True
            continue
        code = _name_line(line)
        if code:
            out.append({"code": code, "lines": [line], "after_end": after_end})
        elif out and (out[-1]["after_end"] or not after_end):
            # Text after END TABLE (an email signature, say) belongs to no block,
            # unless a block itself started there.
            out[-1]["lines"].append(line)
    return out


def _block_problems(b: dict) -> tuple[list[str], str]:
    """What is wrong with one block, and where its key line is.

    GTOCNL re-reads the station name from the third line after the name line
    (``//`` skips two records), so a ``$$ CODE,`` key line must be there.
    merge_blq.py moves one that comes earlier; one that is missing or later
    leaves the station unmatched.
    """
    lines = b["lines"]
    numeric = [ln for ln in lines[1:] if not ln.strip().startswith("$$") and ln.strip()]
    good = [
        ln
        for ln in numeric
        if len(ln.split()) == 11 and all(_float(v) is not None for v in ln.split())
    ]
    problems = []
    if len(good) != 6:
        problems.append(
            f"{len(good)} rows of 11 numbers (Bernese needs 6: three amplitude rows, then three phase rows)"
        )
    if len(numeric) != len(good):
        problems.append(
            f"{len(numeric) - len(good)} other line(s) inside the block that are not 11 numbers"
        )
    # GTOCNL compares columns 4-7 of that line with the code (OLNUMB(2:5)).
    key = next(
        (
            i
            for i, ln in enumerate(lines[1:], 1)
            if ln.startswith("$$") and ln[3:7].upper() == b["code"]
        ),
        None,
    )
    if key is None:
        problems.append(f"no '$$ {b['code']},' key line: GTOCNL would not match the station")
        where = "missing"
    elif key < 3:
        where = "early"  # merge_blq.py pads it to the third line
    elif key == 3:
        where = "ok"
    else:
        problems.append(
            f"the key line is line {key} after the name, not line 3: GTOCNL would not match"
        )
        where = "late"
    return problems, where


# --------------------------------------------------------------------------- the three helpers


def onsala_request(s: Settings, c: Campaign, year: int) -> dict:
    """The lines to paste into the Onsala form for the STA's stations missing from the BLQ."""
    files = campaign_files(s, c, year)
    text = {
        ext: files[ext].read_text(errors="replace") if files[ext].is_file() else ""
        for ext in ("STA", "CRD", "BLQ")
    }
    in_sta = stations_in("STA", text["STA"])
    in_blq = stations_in("BLQ", text["BLQ"])
    crd = read_crd(text["CRD"])
    by_code: dict[str, list[tuple[str, list[float]]]] = {}
    for name, row in crd["stations"].items():
        by_code.setdefault(name[:4], []).append((name, row["xyz"]))
    lines, no_coordinates, ambiguous = [], [], []
    for code in sorted(set(in_sta) - set(in_blq)):
        found = by_code.get(code, [])
        if not found:
            no_coordinates.append(code)
            continue
        if len(found) > 1:
            ambiguous.append(f"{code}: {', '.join(n for n, _ in found)}")
        x, y, z = found[0][1]
        lines.append(f"{code} {x:.5f} {y:.5f} {z:.5f}")
    return {
        "campaign": c.name,
        "sta": files["STA"].name,
        "crd": files["CRD"].name,
        "crd_datum": crd["datum"],
        "crd_epoch": crd["epoch"],
        "blq": files["BLQ"].name,
        "lines": lines,
        "no_coordinates": no_coordinates,
        "two_names": ambiguous,
        # What to choose on the form, so new blocks match the ones already there.
        "settings": blq_settings(text["BLQ"]),
        "form": "https://holt.oso.chalmers.se/loading/",
    }


def check_blq_reply(s: Settings, c: Campaign, year: int, reply: str) -> dict:
    """The Onsala reply, checked against the campaign's BLQ. Writes nothing."""
    files = campaign_files(s, c, year)
    blq_path = files["BLQ"]
    target = blq_path.read_text(errors="replace") if blq_path.is_file() else ""
    in_blq = stations_in("BLQ", target)
    # Bernese never reads these; merge_blq.py counts them as present and skips
    # them, and --replace rewrites them where they are, still after the marker.
    hidden = {b["code"] for b in blq_blocks(target) if b["after_end"]} - set(in_blq)
    in_sta = (
        stations_in("STA", files["STA"].read_text(errors="replace"))
        if files["STA"].is_file()
        else {}
    )
    blocks = blq_blocks(reply)
    problems: list[str] = []
    if not blocks:
        hint = (
            " It looks like a quoted-printable email body (=20, =3D): copy the plain text."
            if re.search(r"=(20|3D)", reply)
            else " Paste the reply's text itself, not the email's HTML."
        )
        problems.append("No station blocks found." + hint)
    rows = []
    seen: set[str] = set()
    for b in blocks:
        why, key = _block_problems(b)
        if b["after_end"]:
            why.append("after '$$ END TABLE' in the reply")
        if b["code"] in seen:
            why.append("twice in the reply")
        seen.add(b["code"])
        if b["code"] in hidden:
            status = f"in {blq_path.name} after '$$ END TABLE', where Bernese never reads it"
            why.append(
                "merge_blq.py treats it as present and leaves it after the marker: move or "
                "delete that block by hand first"
            )
        elif b["code"] in in_blq:
            status = "already in the BLQ: merge_blq.py skips it unless given --replace"
        elif b["code"] not in in_sta:
            status = f"not in {files['STA'].name}: no run of this campaign reads it"
        else:
            status = "new"
        rows.append({"station": b["code"], "status": status, "key_line": key, "problems": why})
    ours, theirs = blq_settings(target), blq_settings(reply)
    differ = [
        f"{k}: the reply has {theirs[k]}, {blq_path.name} has {ours[k]}"
        for k in ours
        if ours[k] and theirs[k] and ours[k].lower() != theirs[k].lower()
    ]
    new = sorted(r["station"] for r in rows if r["status"] == "new" and not r["problems"])
    # Ready means the merge would add something: a reply of stations already
    # present or not in the STA leaves the BLQ as it is.
    ready = bool(new) and not problems and not differ and all(not r["problems"] for r in rows)
    return {
        "campaign": c.name,
        "blq": str(blq_path),
        "stations": rows,
        "problems": problems,
        "settings_differ": differ,
        "new": new,
        "ready": ready,
        # The maintainer's step: a dry run first, then --apply. Never run from here.
        "command": f"scripts/merge_blq.py --blq {blq_path} --new <the reply, saved as a file>",
    }


def final_crds(s: Settings, c: Campaign, year: int) -> list[str]:
    sta = year_dir(s, c.pcf, c.name, year) / "STA"
    return sorted(p.name for p in sta.glob(f"FIN_{year}???0.CRD")) if sta.is_dir() else []


def apriori_preview(s: Settings, c: Campaign, year: int, final: str | None = None) -> dict:
    """A final CRD against the a priori CRD: what "use as a priori" would change.

    Only stations the final solution estimated (a flag in its CRD) count; the
    rest of a final CRD is the a priori carried through unchanged. ``final``
    defaults to the year's latest FIN_*.CRD.
    """
    names = final_crds(s, c, year)
    if final is None:
        final = names[-1] if names else None
    if final is not None and final not in names:
        raise KeyError(f"no {final} in {c.name} {year}")
    apr_path = campaign_files(s, c, year)["CRD"]
    apr = read_crd(apr_path.read_text(errors="replace")) if apr_path.is_file() else read_crd("")
    fin = (
        read_crd((year_dir(s, c.pcf, c.name, year) / "STA" / final).read_text(errors="replace"))
        if final
        else read_crd("")
    )
    rows = []
    estimated = {n: r for n, r in fin["stations"].items() if r["flag"]}
    for name, r in estimated.items():
        a = apr["stations"].get(name)
        if a is None:
            rows.append({"station": name, "change": "added", "neu_mm": None, "horizontal_mm": None})
            continue
        d = [f - p for f, p in zip(r["xyz"], a["xyz"], strict=True)]
        n, e, u = (v * 1000 for v in to_neu(a["xyz"], d))
        rows.append(
            {
                "station": name,
                "change": "moved",
                "neu_mm": [round(n, 1), round(e, 1), round(u, 1)],
                "horizontal_mm": round(math.hypot(n, e), 1),
            }
        )
    rows.sort(key=lambda r: (r["horizontal_mm"] is None, -(r["horizontal_mm"] or 0)))
    not_estimated = sorted(set(apr["stations"]) - set(estimated))
    warnings = []
    if apr["datum"] and fin["datum"] and apr["datum"] != fin["datum"]:
        warnings.append(
            f"The a priori is {apr['datum']} and the final is {fin['datum']}: the differences "
            "include the change of frame, not only new positions."
        )
    if apr["epoch"] and fin["epoch"] and apr["epoch"] != fin["epoch"]:
        warnings.append(
            f"The a priori epoch is {apr['epoch']} and the final's is {fin['epoch']}: "
            "the differences include the stations' motion between the two."
        )
    return {
        "campaign": c.name,
        "apriori": {"file": apr_path.name, "datum": apr["datum"], "epoch": apr["epoch"]},
        "final": {"file": final, "datum": fin["datum"], "epoch": fin["epoch"]},
        "finals": names,
        "rows": rows,
        "not_estimated": not_estimated,
        "warnings": warnings,
    }
