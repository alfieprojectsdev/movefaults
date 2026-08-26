"""
CRD -> ENU -> PLOT files: the plumbing that was never ported.

`crd_pipeline.crd_directory_to_enu` already reproduces steps 01-03 of the
legacy chain and returns `StationEpoch` objects in memory. Two things were
missing, and their absence is why `RUNX_v2.py` is still what gets run:

* **the network filter** — `analysis/02 Time Series/00_CRD_{NP,NAMRIA,PIVS}.bat`,
  three near-identical Windows scripts whose entire content is one `findstr /V`
  with ~270 station codes inlined on a single line. Now `networks.yml`.
* **the PLOT writer** — step 04, the per-site series files that
  `analysis.estimate_velocity`, `make_velocity_field.py` and the
  velocity-reviewer all consume.

Behaviour deliberately kept from `RUNX_v2.py`:

* PLOT line format is ``{decimal_year:.4f}  {E:>13}  {N:>13}  {U:>13}`` — the
  reviewer and `compare_velocity_outlier_policy.py` both parse it.
* A ``123`` file listing the site codes is written beside the series, because
  downstream tooling looks for it.

Behaviour deliberately changed:

* **Idempotent.** `RUNX_v2.py` appends to `XYZ`, `ENU` and every per-site file
  with no truncation, so running it twice silently doubles every series. This
  writes whole files.
* The reference station is a parameter, not an `input()` prompt.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .crd_pipeline import StationEpoch, crd_directory_to_enu

_NETWORKS_FILE = Path(__file__).parent / "networks" / "networks.yml"


@dataclass(frozen=True)
class Network:
    """A named station-exclusion set, loaded from ``networks.yml``."""

    name: str
    description: str
    exclusions: frozenset[str]

    def keeps(self, station: str) -> bool:
        return station.upper() not in self.exclusions


@lru_cache(maxsize=1)
def _load_raw() -> dict:
    with _NETWORKS_FILE.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def available_networks() -> list[str]:
    return sorted(_load_raw()["networks"])


def load_network(name: str) -> Network:
    """Load one network definition by name (case-insensitive).

    Raises:
        KeyError: naming the networks that do exist, because a typo here
            silently processes the wrong station set and nothing downstream
            would notice.
    """
    raw = _load_raw()
    common = {s.upper() for s in raw.get("common_exclusions", [])}
    key = next((k for k in raw["networks"] if k.upper() == name.upper()), None)
    if key is None:
        raise KeyError(f"Unknown network {name!r}. Available: {', '.join(available_networks())}")
    entry = raw["networks"][key] or {}
    extra = {s.upper() for s in (entry.get("extra_exclusions") or [])}
    return Network(
        name=key,
        description=(entry.get("description") or "").strip(),
        exclusions=frozenset(common | extra),
    )


def filter_epochs(epochs: list[StationEpoch], network: Network) -> list[StationEpoch]:
    """Drop epochs whose station the network excludes."""
    return [e for e in epochs if network.keeps(e.station)]


def write_plot_files(
    epochs: list[StationEpoch],
    out_dir: Path,
    *,
    write_site_list: bool = True,
) -> dict[str, Path]:
    """Write one PLOT file per station; return ``{station: path}``.

    Files are written whole, not appended. `RUNX_v2.py` appends with no
    truncation, so a second run doubles every series -- a failure that looks
    like extra data rather than an error.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    by_station: dict[str, list[StationEpoch]] = {}
    for e in epochs:
        by_station.setdefault(e.station, []).append(e)

    written: dict[str, Path] = {}
    for station, rows in sorted(by_station.items()):
        rows.sort(key=lambda r: r.decimal_year)
        path = out_dir / station
        with path.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(
                    f"{r.decimal_year:.4f}  {r.east_m:>13.4f}  "
                    f"{r.north_m:>13.4f}  {r.up_m:>13.4f}\n"
                )
        written[station] = path

    if write_site_list:
        (out_dir / "123").write_text(
            "".join(f"{s}\n" for s in sorted(written)), encoding="utf-8"
        )
    return written


def crd_directory_to_plots(
    crd_dir: Path,
    out_dir: Path,
    reference_station: str,
    network_name: str,
) -> dict[str, Path]:
    """The whole legacy chain, 00 through 04, in one call."""
    network = load_network(network_name)
    epochs = crd_directory_to_enu(crd_dir, reference_station)
    kept = filter_epochs(epochs, network)
    if not kept:
        raise ValueError(
            f"Network {network.name!r} excluded every station in {crd_dir}. "
            "Check the network name and the reference station."
        )
    return write_plot_files(kept, out_dir)
