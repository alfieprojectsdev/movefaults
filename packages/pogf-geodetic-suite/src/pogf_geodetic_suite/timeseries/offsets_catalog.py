"""Load and validate the PHIVOLCS `offsets` discontinuity catalog.

The catalog is a hand-maintained, whitespace-delimited file:

    STATION  DECIMAL_YEAR  TYPE
    BOGO     2019.1561     EQ

It is a load-bearing scientific input — every segmented velocity depends on
it — and until now nothing in this repository read it. `OffsetEvent` values
were hand-constructed by callers, so the file's own integrity was never
checked by anything except a human eye.

WHY THIS MODULE EXISTS

Records that are out of chronological order within a station are not a
cosmetic problem. `vel_line_v8_newvelduetooffset_v4.m` builds its segment
bounds in file order; a descending range makes its `for N=length(...)` loop
never execute, which leaves the PREVIOUS segment's design matrix in place and
fits stale timestamps against current data. The affected sites' published
velocities are simply wrong, with no error raised and nothing in the output
indicating it.

`analysis.py` sorts its segment bounds and is immune. The exposure is to the
MATLAB, which PHIVOLCS staff still run.

So: `load_offsets_catalog` sorts, making consumers safe; `validate_offsets_catalog`
reports without fixing, so defects get corrected at the source rather than
silently absorbed by every reader.

A NOTE ON CHANGING THE CATALOG

A velocity solution is only meaningful alongside the exact catalog that
produced it. If you correct this file, published velocities computed from the
old version do not automatically become comparable to new ones — see the
verification note in `analysis.py`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .analysis import OffsetEvent, OffsetType

__all__ = [
    "CatalogFinding",
    "load_offsets_catalog",
    "validate_offsets_catalog",
]


@dataclass(frozen=True)
class CatalogFinding:
    """One problem found in the catalog.

    `line` is 1-indexed to match what an editor shows.
    """
    line: int
    station: str | None
    kind: str        # "malformed" | "bad_epoch" | "unknown_type" | "out_of_order" | "duplicate"
    detail: str

    def __str__(self) -> str:  # pragma: no cover - convenience only
        where = f"line {self.line}"
        if self.station:
            where += f" ({self.station})"
        return f"{where}: {self.kind} - {self.detail}"


def _parse_line(raw: str) -> tuple[str, float, str] | None:
    """Split one catalog line. Returns None for blank/comment lines."""
    text = raw.split("#", 1)[0].strip()
    if not text:
        return None
    parts = text.split()
    if len(parts) < 3:
        raise ValueError(f"expected 'STATION EPOCH TYPE', got {len(parts)} field(s)")
    station, epoch_s, type_s = parts[0], parts[1], parts[2]
    try:
        epoch = float(epoch_s)
    except ValueError as exc:
        raise ValueError(f"epoch {epoch_s!r} is not a decimal year") from exc
    return station, epoch, type_s.upper()


def load_offsets_catalog(path: str | Path) -> dict[str, list[OffsetEvent]]:
    """Parse the catalog into per-station event lists, sorted by epoch.

    Sorting here is deliberate and matches `analysis.py`: a consumer of this
    function cannot be bitten by file ordering. Use `validate_offsets_catalog`
    when you want to know whether the file itself is well-formed.

    Raises ValueError on a malformed line or an unrecognised offset type,
    naming the line number — a catalog that cannot be read must not be
    half-read.
    """
    path = Path(path)
    by_station: dict[str, list[OffsetEvent]] = {}

    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            try:
                parsed = _parse_line(raw)
            except ValueError as exc:
                raise ValueError(f"{path}:{lineno}: {exc}") from exc
            if parsed is None:
                continue
            station, epoch, type_s = parsed
            try:
                offset_type = OffsetType(type_s)
            except ValueError as exc:
                valid = ", ".join(t.value for t in OffsetType)
                raise ValueError(
                    f"{path}:{lineno}: unknown offset type {type_s!r} "
                    f"(expected one of: {valid})"
                ) from exc
            by_station.setdefault(station, []).append(
                OffsetEvent(date=epoch, offset_type=offset_type)
            )

    for events in by_station.values():
        events.sort(key=lambda e: e.date)
    return by_station


def validate_offsets_catalog(path: str | Path) -> list[CatalogFinding]:
    """Check the catalog without modifying or sorting it.

    Returns findings in line order; an empty list means the file is clean.
    Unlike `load_offsets_catalog`, this does not raise on a bad line — the
    point is to report every problem in one pass, not to stop at the first.
    """
    path = Path(path)
    findings: list[CatalogFinding] = []
    # station -> (last epoch seen, line it was on)
    last_seen: dict[str, tuple[float, int]] = {}
    seen_pairs: dict[tuple[str, float], int] = {}

    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            try:
                parsed = _parse_line(raw)
            except ValueError as exc:
                findings.append(
                    CatalogFinding(lineno, None, "malformed", str(exc))
                )
                continue
            if parsed is None:
                continue
            station, epoch, type_s = parsed

            if type_s not in {t.value for t in OffsetType}:
                valid = ", ".join(t.value for t in OffsetType)
                findings.append(
                    CatalogFinding(
                        lineno, station, "unknown_type",
                        f"{type_s!r} is not one of: {valid}",
                    )
                )

            if not (1980.0 <= epoch <= 2100.0):
                findings.append(
                    CatalogFinding(
                        lineno, station, "bad_epoch",
                        f"{epoch} is outside the plausible GNSS era (1980-2100)",
                    )
                )

            prior = seen_pairs.get((station, epoch))
            if prior is not None:
                findings.append(
                    CatalogFinding(
                        lineno, station, "duplicate",
                        f"epoch {epoch} already recorded on line {prior}",
                    )
                )
            else:
                seen_pairs[(station, epoch)] = lineno

            previous = last_seen.get(station)
            if previous is not None and epoch < previous[0]:
                findings.append(
                    CatalogFinding(
                        lineno, station, "out_of_order",
                        f"epoch {epoch} precedes {previous[0]} on line {previous[1]}; "
                        "the MATLAB builds segment bounds in file order and fits "
                        "stale timestamps when the range descends",
                    )
                )
            last_seen[station] = (epoch, lineno)

    return findings
