"""
2-D dislocation model on a velocity profile, with the bootstrap: a faithful port.

PORT OF the Leyte working copies of ``velproj_loop.m``,
``makeG_2ds_v3_loop.m`` and ``bootstrap_v2.py`` (``analysis/08
Bootstrapping``, as run in November 2026), following
``docs/project_documentation/porting_method.md``: faithful first, each known
defect behind a named switch whose default is the legacy behaviour.

Checked against one MATLAB iteration per Leyte segment (``parameters.txt``
with the ``PHm.txt`` and ``2D_PH.mat`` that produced it): every grid row
agrees, slip to 1.4e-7 relative and the misfits to 1e-11, and both picks are
the same model. The reference files are PHIVOLCS data and stay outside the
repository; ``tests/test_profile2d.py`` runs that check where they exist.

THE PIPELINE
------------
1. ``project``: each station's velocity onto the direction normal to the
   profile (``Vortho``), its distance along the profile from a reference point
   on the fault (``x_km``), keeping stations within ``halfwidth_km`` of the
   line, sorted by distance (``velproj_loop.m``).
2. ``drop_reference``: ``makeG_2ds_v3_loop.m`` removes the FIRST station after
   sorting, assuming it is the reference station (which carries no velocity).
3. ``green_table``: the north displacement for unit strike-slip on a 1000 km
   long fault, for every (E1, depth, width, dip). It doesn't depend on the data
   or on the block rate, so it is computed once per station set: the reason a
   bootstrap iteration takes well under a second here and about 1.5 h in MATLAB.
4. ``grid``: for every geometry and block rate, the weighted least-squares
   slip and its misfits, exactly as the MATLAB's backslash computes them.
5. ``legacy_picks``: ``bootstrap_v2.py``'s two picks, among models with
   0 <= slip <= rate: reduced chi-square closest to 1, and every model at the
   minimum WRMS.

LEGACY SWITCHES, AND WHAT EACH ONE FIXES
----------------------------------------
``sigma="legacy" | "propagated"``
    Legacy: ``sqrt(sE^2 + sN^2) * |sin(azimuth - Az)|``, which scales the
    error by the station's own velocity direction. Propagated: the
    profile-normal component is ``-vE cos(Az) + vN sin(Az)``, so its 1-sigma
    is ``sqrt((sE cos Az)^2 + (sN sin Az)^2)``. On Southern Leyte the legacy
    error is 0.07-1.76 times the propagated one depending on the station.
``drop="first" | "reference"``
    First: remove the first station along the profile, as the MATLAB does.
    Reference: remove the named reference station wherever it sorts. They
    agree whenever the reference is the westernmost station (true for both
    Leyte segments), and differ only when a resampled site lies beyond it.

WHAT IS NOT HERE YET
--------------------
The changes ``fault_model_priors.md`` recommends (dip fixed and the buried
edge estimated, null / creep-step / locked models, minimum chi-square,
jackknife) come as further switches, each with a delta report. Figures and the
command line come after them.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from .disloc import disloc

D2R = np.pi / 180.0

Sigma = Literal["legacy", "propagated"]
Drop = Literal["first", "reference"]

# The velocity table's columns (PHm.csv / PHm.txt), as bootstrap_v2.py writes them.
COLUMNS = [
    "sites", "Ecoord", "Ncoord", "height", "velocity", "azimuth",
    "Vu", "hgt", "erreast", "errnorth",
]  # fmt: skip
# parameters.txt, in the MATLAB's column order.
PARAMETER_COLUMNS = [
    "East", "Depth", "Width", "Dip", "Residual", "Rate", "Slip", "Reduced chi2", "Chi2",
]  # fmt: skip


@dataclass(frozen=True)
class Profile:
    """Where the profile is and which stations it keeps (velproj_loop.m's inputs)."""

    azimuth_deg: float  # profile direction, from north, clockwise (the MATLAB's Az)
    origin_en: tuple[float, float]  # projected (E, N) of the point distances are from
    halfwidth_km: float = 200.0  # stations within this distance of the line (the MATLAB's width)


@dataclass(frozen=True)
class Grid:
    """The search axes (makeG_2ds_v3_loop.m's loops), outermost first."""

    e1: np.ndarray  # fault's east offset along the profile, km
    depth: np.ndarray  # km
    width: np.ndarray  # km
    dip: np.ndarray  # degrees
    rate: np.ndarray  # block rate, mm/yr

    @property
    def shape(self) -> tuple[int, int, int, int, int]:
        return (len(self.e1), len(self.depth), len(self.width), len(self.dip), len(self.rate))

    @property
    def size(self) -> int:
        return int(np.prod(self.shape))

    def as_lists(self) -> dict[str, list[float]]:
        return {
            k: [float(v) for v in getattr(self, k)] for k in ("e1", "depth", "width", "dip", "rate")
        }


@dataclass(frozen=True)
class ProfileData:
    """Stations on the profile, sorted along it."""

    sites: np.ndarray  # str
    x_km: np.ndarray
    v_orth: np.ndarray  # mm/yr, profile-normal
    err: np.ndarray  # mm/yr, 1-sigma, per `sigma`

    def take(self, idx: np.ndarray | Sequence[int]) -> ProfileData:
        idx = np.asarray(idx)
        return ProfileData(self.sites[idx], self.x_km[idx], self.v_orth[idx], self.err[idx])

    def __len__(self) -> int:
        return len(self.x_km)


@dataclass
class GridResult:
    """Every model's slip and misfits, shape `grid.shape`."""

    grid: Grid
    slip: np.ndarray
    chi2: np.ndarray
    reduced_chi2: np.ndarray
    wrms: np.ndarray

    def table(self) -> pd.DataFrame:
        """parameters.txt as a DataFrame: one row per model, the MATLAB's loop order."""
        g = self.grid
        E, D, W, P, R = np.meshgrid(g.e1, g.depth, g.width, g.dip, g.rate, indexing="ij")
        return pd.DataFrame(
            {
                "East": E.ravel(), "Depth": D.ravel(), "Width": W.ravel(), "Dip": P.ravel(),
                "Residual": self.wrms.ravel(), "Rate": R.ravel(), "Slip": self.slip.ravel(),
                "Reduced chi2": self.reduced_chi2.ravel(), "Chi2": self.chi2.ravel(),
            }
        )  # fmt: skip

    def model(self, flat_index: int) -> dict[str, float]:
        """One model's parameters and results, by its row in `table()`."""
        a, b, c, k, r = np.unravel_index(flat_index, self.grid.shape)
        g = self.grid
        return {
            "East": float(g.e1[a]), "Depth": float(g.depth[b]), "Width": float(g.width[c]),
            "Dip": float(g.dip[k]), "Residual": float(self.wrms.flat[flat_index]),
            "Rate": float(g.rate[r]), "Slip": float(self.slip.flat[flat_index]),
            "Reduced chi2": float(self.reduced_chi2.flat[flat_index]),
            "Chi2": float(self.chi2.flat[flat_index]),
        }  # fmt: skip


# ── 1. projection ────────────────────────────────────────────────────────────


def read_velocities(path: str | Path) -> pd.DataFrame:
    """A PHm.csv (comma) or PHm.txt (tab) velocity table, with its header row."""
    text = Path(path).read_text()
    sep = "\t" if "\t" in text.splitlines()[0] else ","
    df = pd.read_csv(path, sep=sep)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")
    return df


def project(df: pd.DataFrame, profile: Profile, *, sigma: Sigma = "legacy") -> ProfileData:
    """velproj_loop.m: profile-normal velocity and distance along the profile.

    Rows are sorted by distance with a stable sort, as MATLAB's `sort` is, so
    duplicated stations (a bootstrap resample) keep their order.
    """
    vel = df["velocity"].to_numpy(float)
    azi = df["azimuth"].to_numpy(float)
    se = df["erreast"].to_numpy(float)
    sn = df["errnorth"].to_numpy(float)
    E = df["Ecoord"].to_numpy(float)
    N = df["Ncoord"].to_numpy(float)

    ang = (azi - profile.azimuth_deg) * D2R
    v_orth = -vel * np.sin(ang)
    if sigma == "legacy":
        err = np.abs(np.sqrt(se**2 + sn**2) * np.sin(ang))
    elif sigma == "propagated":
        a = profile.azimuth_deg * D2R
        err = np.sqrt((se * np.cos(a)) ** 2 + (sn * np.sin(a)) ** 2)
    else:
        raise ValueError(f"sigma must be 'legacy' or 'propagated', not {sigma!r}")

    idx, along = _on_profile(E, N, profile)
    return ProfileData(
        df["sites"].to_numpy(str)[idx].astype(str), along[idx], v_orth[idx], err[idx]
    )


def _on_profile(E: np.ndarray, N: np.ndarray, profile: Profile) -> tuple[np.ndarray, np.ndarray]:
    """Rows within the band, sorted along the profile (stable), and every row's distance in km."""
    th = profile.azimuth_deg * D2R
    e0, n0 = profile.origin_en
    across = (-(E - e0) * np.cos(th) + (N - n0) * np.sin(th)) / 1000.0
    along = ((E - e0) * np.sin(th) + (N - n0) * np.cos(th)) / 1000.0
    keep = np.flatnonzero(np.abs(across) <= profile.halfwidth_km)
    return keep[np.argsort(along[keep], kind="stable")], along


def drop_reference(
    data: ProfileData, *, drop: Drop = "first", reference: str | None = None
) -> ProfileData:
    """Remove the reference station before fitting.

    "first" is the MATLAB's `Vorth(2:end)`: the first station along the
    profile, assumed to be the reference. "reference" removes every row named
    `reference`, wherever it sorts.
    """
    return data.take(_kept(data, drop, reference))


def _kept(data: ProfileData, drop: Drop, reference: str | None) -> np.ndarray:
    """Positions `drop_reference` keeps."""
    if drop == "first":
        return np.arange(1, len(data))
    if drop == "reference":
        if not reference:
            raise ValueError("drop='reference' needs the reference station's name")
        keep = np.flatnonzero(np.char.strip(data.sites.astype(str)) != reference.strip())
        if len(keep) == len(data):
            raise ValueError(f"{reference} is not on the profile")
        return keep
    raise ValueError(f"drop must be 'first' or 'reference', not {drop!r}")


# ── 2. Green's functions ─────────────────────────────────────────────────────


def green_table(x_km: np.ndarray, grid: Grid, *, nu: float = 0.25) -> np.ndarray:
    """North displacement for unit strike-slip, shape (n_e1, n_depth, n_width, n_dip, n_station).

    The MATLAB's fault row is [1000, W, D, -180 + dip, 0, E1, 0] with unit
    strike-slip, and only the north component is kept (`G11(2:3:end)`). A
    zero-width fault displaces nothing, so its column is left at 0.
    """
    x_km = np.asarray(x_km, float)
    out = np.zeros(grid.shape[:4] + (len(x_km),))
    coords = np.vstack([x_km, np.zeros_like(x_km)])
    model = np.zeros((10, 1))
    model[0] = 1000.0
    model[7] = 1.0
    for a, e1 in enumerate(grid.e1):
        model[5] = e1
        for b, d in enumerate(grid.depth):
            model[2] = d
            for c, w in enumerate(grid.width):
                if w == 0:
                    continue
                model[1] = w
                for k, dip in enumerate(grid.dip):
                    model[3] = -180.0 + dip
                    out[a, b, c, k] = disloc(model, coords, nu=nu, strict=False)[1]
    return out


# ── 3. the grid ──────────────────────────────────────────────────────────────


def solve_grid(G: np.ndarray, data: ProfileData, grid: Grid) -> GridResult:
    """Every model of makeG_2ds_v3_loop.m, vectorised.

    Stations at x >= 0 move with the block: their data is Vorth - rate. The
    slip is the weighted least-squares solution `(C G) \\ (C d)` with
    C = diag(1/err); with one unknown that is sum(w g d) / sum(w g^2), and a
    zero G (zero width) gives slip 0, as MATLAB's backslash does.
    """
    x, v, err = data.x_km, data.v_orth, data.err
    if G.shape[-1] != len(x):
        raise ValueError(f"G has {G.shape[-1]} stations, the data {len(x)}")
    if np.any(err <= 0):
        raise ValueError("every station needs a positive error")
    w = 1.0 / err**2
    east = x >= 0
    d = v[None, :] - grid.rate[:, None] * east[None, :]  # (n_rate, n_station)
    Gw = G * w
    gg = (Gw * G).sum(-1)[..., None]  # (..., 1)
    gd = np.einsum("...s,rs->...r", Gw, d)
    with np.errstate(invalid="ignore", divide="ignore"):
        slip = np.where(gg > 0, gd / gg, 0.0)
    dd = (d**2 * w).sum(-1)  # (n_rate,)
    # chi2 = sum w (d - s g)^2, expanded so no (models x stations) array is built.
    chi2 = np.maximum(dd - 2 * slip * gd + slip**2 * gg, 0.0)
    return GridResult(
        grid=grid,
        slip=slip,
        chi2=chi2,
        reduced_chi2=chi2 / len(x),
        wrms=np.sqrt(chi2 / w.sum()),
    )


# ── 4. picks ─────────────────────────────────────────────────────────────────


def legacy_picks(result: GridResult) -> tuple[int, np.ndarray]:
    """bootstrap_v2.py's picks among models with 0 <= slip <= rate.

    Returns the flat index of the model whose reduced chi-square is closest
    to 1, and the flat indices of every model at the minimum WRMS (the script
    appends all of them). Raises ValueError if no model passes the filter.
    """
    rate = np.broadcast_to(result.grid.rate, result.slip.shape)
    ok = (result.slip >= 0) & (result.slip <= rate)
    if not ok.any():
        raise ValueError("no model has 0 <= slip <= rate")
    closeness = np.where(ok, np.abs(result.reduced_chi2 - 1.0), np.inf).ravel()
    wrms = np.where(ok, result.wrms, np.inf).ravel()
    i_rchi = int(np.argmin(closeness))
    i_wrms = np.flatnonzero(wrms == wrms.min())
    return i_rchi, i_wrms


# ── 5. the bootstrap ─────────────────────────────────────────────────────────


@dataclass
class BootstrapRun:
    """What one bootstrap run produced, and how."""

    rchi_picks: list[dict[str, float]]  # one per iteration
    wrms_picks: list[list[dict[str, float]]]  # every tied model, per iteration
    settings: dict = field(default_factory=dict)

    def intervals(
        self, which: str = "rchi", q: tuple[float, float] = (0.025, 0.975)
    ) -> pd.DataFrame:
        """bootstrap_v2.py's plot(): quantiles of each parameter over the picks."""
        rows = self.rchi_picks if which == "rchi" else [m for it in self.wrms_picks for m in it]
        df = pd.DataFrame(rows)[["East", "Depth", "Width", "Dip", "Rate", "Slip"]]
        return df.quantile([q[0], 0.5, q[1]]).T.rename(
            columns={q[0]: "low", 0.5: "median", q[1]: "high"}
        )


def bootstrap(
    population: pd.DataFrame,
    reference_row: pd.DataFrame,
    profile: Profile,
    grid: Grid,
    *,
    n_samples: int,
    sample_size: int,
    seed: int,
    sigma: Sigma = "legacy",
    drop: Drop = "first",
    nu: float = 0.25,
) -> BootstrapRun:
    """bootstrap_v2.py's start(), with a seed.

    Each iteration draws `sample_size` rows of `population` with replacement,
    appends the reference row, projects, drops the reference and runs the
    grid. Projection is per station, so the Green's functions are computed
    once for the population and each resample takes its columns.

    The MATLAB's random draws can't be reproduced (pandas' unseeded global
    state); a seeded run is compared with it by distribution, not row by row.
    """
    reference = str(reference_row["sites"].iloc[0]).strip()
    both = pd.concat([population, reference_row], ignore_index=True)
    projected = project(both, profile, sigma=sigma)
    # Projected position of each row of `both`; rows outside the band have none,
    # as velproj_loop.m would drop them from any resample.
    order, _ = _on_profile(both["Ecoord"].to_numpy(float), both["Ncoord"].to_numpy(float), profile)
    position = {int(row): p for p, row in enumerate(order)}
    if len(both) - 1 not in position:
        raise ValueError(f"the reference {reference} is outside the profile band")
    G_all = green_table(projected.x_km, grid, nu=nu)

    rng = np.random.default_rng(seed)
    rchi_picks: list[dict[str, float]] = []
    wrms_picks: list[list[dict[str, float]]] = []
    for _ in range(n_samples):
        draw = rng.choice(len(population), size=sample_size, replace=True)
        # The resample in draw order with the reference appended, then sorted
        # along the profile with a stable sort: what velproj_loop.m sees.
        rows = [position[int(i)] for i in draw if int(i) in position] + [position[len(both) - 1]]
        rows = np.asarray(sorted(rows, key=lambda p: projected.x_km[p]))
        sample = projected.take(rows)
        keep = _kept(sample, drop, reference)
        result = solve_grid(G_all[..., rows[keep]], sample.take(keep), grid)
        i_r, i_w = legacy_picks(result)
        rchi_picks.append(result.model(i_r))
        wrms_picks.append([result.model(int(i)) for i in i_w])

    settings = {
        "n_samples": n_samples,
        "sample_size": sample_size,
        "seed": seed,
        "sigma": sigma,
        "drop": drop,
        "nu": nu,
        "reference": reference,
        "profile": asdict(profile),
        "grid": grid.as_lists(),
        "population_sha256": _frame_sha256(population),
    }
    return BootstrapRun(rchi_picks, wrms_picks, settings)


def _frame_sha256(df: pd.DataFrame) -> str:
    return hashlib.sha256(df.to_csv(index=False).encode()).hexdigest()


# ── output in the MATLAB's formats ───────────────────────────────────────────


def _fmt(v: float) -> str:
    return f"{v:.15g}"


def write_parameters(result: GridResult, path: str | Path) -> None:
    """parameters.txt as MATLAB's writetable writes it: a header, spaces, 15 significant digits."""
    t = result.table()
    lines = [" ".join(f'"{c}"' if " " in c else c for c in PARAMETER_COLUMNS)]
    cols = [t[c].to_numpy() for c in PARAMETER_COLUMNS]
    lines += [" ".join(_fmt(col[i]) for col in cols) for i in range(len(t))]
    Path(path).write_text("\n".join(lines) + "\n")


def pick_line(model: dict[str, float]) -> str:
    """One row of parameters_rchi.txt / parameters_wrms.txt (tab-separated, no header)."""
    return "\t".join(_fmt(model[c]) for c in PARAMETER_COLUMNS)


def write_manifest(run: BootstrapRun, path: str | Path) -> None:
    """The settings that produced a bootstrap run, beside its outputs."""
    Path(path).write_text(json.dumps(run.settings, indent=2) + "\n")
