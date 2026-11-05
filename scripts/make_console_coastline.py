#!/usr/bin/env python3
"""Write the coastline the BSW console's station map draws.

    npm pack world-atlas@2.0.2 && tar xzf world-atlas-2.0.2.tgz
    python3 scripts/make_console_coastline.py package/land-50m.json package/land-10m.json

The map needs no tile server: gps3's pages must work on the office network alone,
and a tile server would learn where every station is. So the land is a file in the
repository, from Natural Earth (public domain) by way of the world-atlas package.
Run this only to change the area or the detail; the output is committed.

It keeps land near the networks this project processes, in two levels of detail:
10m around the Philippines, where the stations are, and 50m out to the IGS
fiducials a campaign uses (Australia, Japan, Korea), which keeps the file small.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "services/bsw-console/frontend/src/coastline.json"
WIDE = (90.0, -50.0, 170.0, 55.0)  # lon, lat, lon, lat
PHILIPPINES = (115.0, 3.0, 128.0, 22.0)


def rings(path: Path) -> list[list[tuple[float, float]]]:
    """The outer and inner rings of a world-atlas land TopoJSON file."""
    topo = json.loads(path.read_text())
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        points = []
        for dx, dy in arc:
            x += dx
            y += dy
            points.append((x * sx + tx, y * sy + ty))
        arcs.append(points)

    def ring(ids: list[int]) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for i in ids:
            arc = arcs[i] if i >= 0 else arcs[~i][::-1]
            out.extend(arc[1:] if out else arc)
        return out

    found = []
    for geometry in topo["objects"]["land"]["geometries"]:
        polygons = geometry["arcs"]
        if geometry["type"] == "Polygon":
            polygons = [polygons]
        for polygon in polygons:
            found.extend(ring(ids) for ids in polygon)
    return found


def inside(ring_: list[tuple[float, float]], box: tuple[float, float, float, float]) -> bool:
    xs = [p[0] for p in ring_]
    ys = [p[1] for p in ring_]
    return max(xs) >= box[0] and min(xs) <= box[2] and max(ys) >= box[1] and min(ys) <= box[3]


def centred_in(ring_: list[tuple[float, float]], box: tuple[float, float, float, float]) -> bool:
    x = sum(p[0] for p in ring_) / len(ring_)
    y = sum(p[1] for p in ring_) / len(ring_)
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def thin(ring_: list[tuple[float, float]], digits: int) -> list[list[float]]:
    out: list[list[float]] = []
    for x, y in ring_:
        p = [round(x, digits), round(y, digits)]
        if not out or p != out[-1]:
            out.append(p)
    if out[0] != out[-1]:
        out.append(out[0])
    return out


def main() -> int:
    coarse, fine = Path(sys.argv[1]), Path(sys.argv[2])
    # A ring that spans the area, Eurasia say, stays at 50m detail: only what lies
    # wholly in the Philippine box is swapped for the finer outline.
    far = [r for r in rings(coarse) if inside(r, WIDE) and not centred_in(r, PHILIPPINES)]
    near = [r for r in rings(fine) if centred_in(r, PHILIPPINES) and len(r) >= 4]
    lines = [thin(r, 1) for r in far] + [thin(r, 3) for r in near]
    lines = [r for r in lines if len(r) >= 4]
    OUT.write_text(
        json.dumps(
            {
                "type": "MultiLineString",
                "coordinates": lines,
                "source": "Natural Earth, public domain, by way of world-atlas 2.0.2; "
                "scripts/make_console_coastline.py",
            },  # fmt: skip
            separators=(",", ":"),
        )
        + "\n"
    )
    print(f"{OUT}: {len(lines)} rings, {OUT.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
