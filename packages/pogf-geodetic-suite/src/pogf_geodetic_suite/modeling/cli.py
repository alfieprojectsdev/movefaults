"""
`pogf-modeling` -- run the 2-D profile model and its bootstrap from a command line.

`profile2d` ports `velproj_loop.m`, `makeG_2ds_v3_loop.m` and `bootstrap_v2.py`,
and until now could only be called from Python. These commands are the three
things the processing team does with those scripts:

    pogf-modeling profile   velocities onto a profile      (velproj_loop.m)
    pogf-modeling grid      every model for one data set   (makeG_2ds_v3_loop.m)
    pogf-modeling bootstrap resample, fit, pick, repeat    (bootstrap_v2.py)

SETTINGS
What the MATLAB keeps as numbers edited inside the scripts (azimuth, origin,
grid limits, sample count) is given here as options, or in a JSON file passed
with `--settings`; an option on the command line wins over the file. Every run
writes the settings it used beside its outputs, in the same shape, so
`--settings <that file>` repeats the run exactly, seed included.

    {"profile": {"azimuth_deg": 73, "origin_en": [596523.77, -1432036.97], "halfwidth_km": 200},
     "grid": {"e1": "-3:3:1", "depth": "0:15:1", "width": "0:15:1", "dip": "65:90:1", "rate": "30:50:1"},
     "reference": "ISAB", "sigma": "legacy", "drop": "first",
     "n_samples": 1000, "sample_size": 12, "seed": 20261116}

A grid axis is "from:to:step" (both ends included, as MATLAB's `a:s:b`) or a
list of values.

DEFAULTS ARE THE MATLAB'S BEHAVIOUR
`sigma` and `drop` default to "legacy" and "first" (see `profile2d`), so the
numbers match the scripts'. The corrected choices are one option away, and the
settings file records which were used.

THE VELOCITY TABLE
`PHm.csv` as the team prepares it: a header row, then one row per station, the
reference station among them (first, in their files). `--reference` names it;
without it the first row is taken, and the command says so.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any

import click
import numpy as np
import pandas as pd

from .profile2d import (
    BootstrapRun,
    Grid,
    Profile,
    bootstrap,
    drop_reference,
    green_table,
    legacy_picks,
    pick_line,
    project,
    read_velocities,
    solve_grid,
    write_parameters,
)

AXES = ("e1", "depth", "width", "dip", "rate")
SETTINGS_NAME = "settings.json"


# ── settings ─────────────────────────────────────────────────────────────────


def parse_axis(value: Any, name: str) -> np.ndarray:
    """A grid axis from "from:to:step" (ends included) or a list of numbers."""
    if isinstance(value, str):
        parts = value.split(":")
        try:
            lo, hi, step = (float(p) for p in parts)
        except ValueError:
            raise click.ClickException(
                f"{name}: expected from:to:step, e.g. 0:15:1, got {value!r}"
            ) from None
        if step <= 0 or hi < lo:
            raise click.ClickException(f"{name}: need step > 0 and to >= from, got {value!r}")
        # Half a step past the end, so 0:15:1 includes 15 whatever the rounding.
        axis = np.arange(lo, hi + step / 2, step, dtype=float)
    else:
        try:
            axis = np.asarray(value, dtype=float).ravel()
        except (TypeError, ValueError):
            raise click.ClickException(f"{name}: expected numbers, got {value!r}") from None
    if axis.size == 0 or not np.all(np.isfinite(axis)):
        raise click.ClickException(f"{name}: no usable values in {value!r}")
    return axis


def _merge(settings_file: Path | None, given: dict[str, Any]) -> dict[str, Any]:
    """The settings file, overridden by whatever was given on the command line."""
    merged: dict[str, Any] = {"profile": {}, "grid": {}}
    if settings_file is not None:
        try:
            loaded = json.loads(settings_file.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise click.ClickException(f"{settings_file}: {exc}") from None
        if not isinstance(loaded, dict):
            raise click.ClickException(f"{settings_file}: expected a JSON object")
        for key, value in loaded.items():
            if key in ("profile", "grid"):
                if not isinstance(value, dict):
                    raise click.ClickException(f"{settings_file}: {key} must be an object")
                merged[key].update(value)
            else:
                merged[key] = value
    for key, value in given.items():
        if value is None or value == ():
            continue
        if key in ("azimuth_deg", "origin_en", "halfwidth_km"):
            merged["profile"][key] = value
        elif key in AXES:
            merged["grid"][key] = value
        else:
            merged[key] = value
    return merged


def _profile(merged: dict[str, Any]) -> Profile:
    p = merged["profile"]
    missing = [
        opt for key, opt in (("azimuth_deg", "--azimuth"), ("origin_en", "--origin")) if key not in p
    ]
    if missing:
        raise click.ClickException(
            "the profile needs " + " and ".join(missing) + " (or the same in --settings)"
        )
    try:
        origin = tuple(float(v) for v in p["origin_en"])
        azimuth = float(p["azimuth_deg"])
        halfwidth = float(p.get("halfwidth_km", 200.0))
    except (TypeError, ValueError):
        raise click.ClickException(f"profile: not numbers: {p!r}") from None
    if len(origin) != 2:
        raise click.ClickException("the profile origin is two numbers: east and north, in metres")
    return Profile(azimuth, origin, halfwidth)  # type: ignore[arg-type]


def _grid(merged: dict[str, Any]) -> Grid:
    g = merged["grid"]
    missing = [f"--{a}" for a in AXES if a not in g]
    if missing:
        raise click.ClickException(
            "the grid needs " + ", ".join(missing) + " (or the same in --settings)"
        )
    return Grid(**{a: parse_axis(g[a], a) for a in AXES})


def _choice(merged: dict[str, Any], key: str, allowed: tuple[str, ...]) -> str:
    value = merged.get(key, allowed[0])
    if value not in allowed:
        raise click.ClickException(f"{key} is one of {', '.join(allowed)}; got {value!r}")
    return value


def _split_reference(df: pd.DataFrame, merged: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """(stations without the reference, the reference's row, its name)."""
    sites = df["sites"].astype(str).str.strip()
    named = merged.get("reference")
    if named:
        name = str(named).strip()
        hits = df.index[sites.str.upper() == name.upper()]
        if len(hits) != 1:
            raise click.ClickException(
                f"the reference {name} is in {len(hits)} rows of the velocity table; it must be in one"
            )
        at = hits[0]
        name = sites.loc[at]  # the table's own spelling, which the later steps match on
    else:
        at = df.index[0]
        name = sites.iloc[0]
        click.echo(f"reference station: {name} (the table's first row; --reference names another)", err=True)
    return df.drop(index=at).reset_index(drop=True), df.loc[[at]].reset_index(drop=True), name


def _record(profile: Profile, grid: Grid | None, **more: Any) -> dict[str, Any]:
    """The settings a run used, in the shape --settings reads."""
    out: dict[str, Any] = {
        "profile": {
            "azimuth_deg": profile.azimuth_deg,
            "origin_en": list(profile.origin_en),
            "halfwidth_km": profile.halfwidth_km,
        }
    }
    if grid is not None:
        out["grid"] = grid.as_lists()
    out.update(more)
    return out


def _out_dir(out: Path, names: list[str], overwrite: bool) -> None:
    """Make `out`, refusing to replace earlier results unless told to.

    bootstrap_v2.py appends to parameters_rchi.txt, so two runs with different
    settings end up in one file with nothing to tell them apart.
    """
    out.mkdir(parents=True, exist_ok=True)
    there = [n for n in names if (out / n).exists()]
    if there and not overwrite:
        raise click.ClickException(
            f"{out} already holds {', '.join(there)}: choose another --out, or pass --overwrite"
        )


def _model_text(model: dict[str, float]) -> str:
    return (
        f"East {model['East']:g} km, depth {model['Depth']:g} km, width {model['Width']:g} km, "
        f"dip {model['Dip']:g}°, rate {model['Rate']:g} mm/yr, slip {model['Slip']:.3f} mm/yr "
        f"(reduced chi2 {model['Reduced chi2']:.4g}, WRMS {model['Residual']:.4g})"
    )


# ── options shared by the commands ───────────────────────────────────────────


def _shared(grid_too: bool):
    def wrap(fn):
        options = [
            click.argument("velocities", type=click.Path(exists=True, dir_okay=False, path_type=Path)),
            click.option("--settings", "settings_file", type=click.Path(exists=True, dir_okay=False, path_type=Path),
                         help="JSON settings; options given here override it."),
            click.option("--azimuth", "azimuth_deg", type=float,
                         help="Profile direction, degrees clockwise from north (the MATLAB's Az)."),
            click.option("--origin", "origin_en", type=float, nargs=2, default=None,
                         help="East and north, in metres, of the point on the fault distances are from."),
            click.option("--halfwidth", "halfwidth_km", type=float,
                         help="Keep stations within this many km of the profile line.  [default: 200]"),
            click.option("--sigma", type=click.Choice(["legacy", "propagated"]),
                         help="legacy: the MATLAB's profile-normal error. propagated: the corrected one.  [default: legacy]"),
        ]  # fmt: skip
        if grid_too:
            options += [
                click.option("--reference", help="The reference station's code.  [default: the table's first row]"),
                click.option("--drop", type=click.Choice(["first", "reference"]),
                             help="first: remove the first station along the profile, as the MATLAB does. "
                                  "reference: remove the reference wherever it sorts.  [default: first]"),
                click.option("--e1", help="Fault's east offset along the profile, km: from:to:step."),
                click.option("--depth", help="Depth, km: from:to:step."),
                click.option("--width", help="Width, km: from:to:step."),
                click.option("--dip", help="Dip, degrees: from:to:step."),
                click.option("--rate", help="Block rate, mm/yr: from:to:step."),
                click.option("--overwrite", is_flag=True, help="Replace results already in --out."),
            ]  # fmt: skip
        for option in reversed(options):
            fn = option(fn)
        return fn

    return wrap


@click.group()
def group() -> None:
    """The 2-D profile dislocation model and its bootstrap, without MATLAB."""


# ── profile ──────────────────────────────────────────────────────────────────


@group.command()
@_shared(grid_too=False)
@click.option("-o", "--out", type=click.Path(dir_okay=False, path_type=Path),
              help="Write the table here as well as printing it.")  # fmt: skip
def profile(velocities: Path, settings_file: Path | None, out: Path | None, **given: Any) -> None:
    """Project velocities onto a profile: velproj_loop.m.

    Prints each station's distance along the profile, its profile-normal
    velocity and that velocity's error, sorted along the profile, for the
    stations within the half-width.

        pogf-modeling profile PHm.csv --azimuth 73 --origin 596523.77 -1432036.97
    """
    merged = _merge(settings_file, given)
    prof = _profile(merged)
    sigma = _choice(merged, "sigma", ("legacy", "propagated"))
    try:
        data = project(read_velocities(velocities), prof, sigma=sigma)  # type: ignore[arg-type]
    except ValueError as exc:
        raise click.ClickException(str(exc)) from None
    lines = [
        f"# profile azimuth {prof.azimuth_deg:g} deg, origin E {prof.origin_en[0]:.4f} N {prof.origin_en[1]:.4f} m, "
        f"half-width {prof.halfwidth_km:g} km, sigma {sigma}",
        "# site   x_km      v_normal_mm_yr  err_mm_yr",
    ]
    lines += [
        f"{s.strip():<6} {x:9.3f} {v:15.5f} {e:10.5f}"
        for s, x, v, e in zip(data.sites, data.x_km, data.v_orth, data.err, strict=True)
    ]
    text = "\n".join(lines) + "\n"
    click.echo(text, nl=False)
    if out is not None:
        out.write_text(text)


# ── grid ─────────────────────────────────────────────────────────────────────


@group.command()
@_shared(grid_too=True)
@click.option("-o", "--out", type=click.Path(file_okay=False, path_type=Path), required=True,
              help="Output directory.")  # fmt: skip
@click.option("--table/--no-table", default=True, show_default=True,
              help="Write parameters.txt, every model's row, as the MATLAB does (about 80 MB for a million models).")  # fmt: skip
def grid(velocities: Path, settings_file: Path | None, out: Path, table: bool, overwrite: bool, **given: Any) -> None:
    """Fit every model of the grid to one data set: makeG_2ds_v3_loop.m.

    Writes parameters.txt (unless --no-table), the two picks bootstrap_v2.py
    makes (parameters_rchi.txt, parameters_wrms.txt) and settings.json.

        pogf-modeling grid PHm.csv --settings leyte_south.json -o run1/
    """
    merged = _merge(settings_file, given)
    prof, axes = _profile(merged), _grid(merged)
    sigma = _choice(merged, "sigma", ("legacy", "propagated"))
    drop = _choice(merged, "drop", ("first", "reference"))
    names = ["parameters_rchi.txt", "parameters_wrms.txt", SETTINGS_NAME] + (["parameters.txt"] if table else [])
    try:
        df = read_velocities(velocities)
        _, _, reference = _split_reference(df, merged)
        data = drop_reference(project(df, prof, sigma=sigma), drop=drop, reference=reference)  # type: ignore[arg-type]
        result = solve_grid(green_table(data.x_km, axes), data, axes)
        i_rchi, i_wrms = legacy_picks(result)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from None
    _out_dir(out, names, overwrite)
    if table:
        write_parameters(result, out / "parameters.txt")
    (out / "parameters_rchi.txt").write_text(pick_line(result.model(i_rchi)) + "\n")
    (out / "parameters_wrms.txt").write_text("".join(pick_line(result.model(int(i))) + "\n" for i in i_wrms))
    record = _record(prof, axes, reference=reference, sigma=sigma, drop=drop,
                     velocities=str(velocities), stations=[s.strip() for s in data.sites])  # fmt: skip
    (out / SETTINGS_NAME).write_text(json.dumps(record, indent=2) + "\n")
    click.echo(f"{axes.size:,} models on {len(data)} stations: {', '.join(s.strip() for s in data.sites)}")
    click.echo(f"reduced chi2 closest to 1: {_model_text(result.model(i_rchi))}")
    click.echo(f"minimum WRMS ({len(i_wrms)} model{'s' if len(i_wrms) != 1 else ''}): "
               f"{_model_text(result.model(int(i_wrms[0])))}")  # fmt: skip
    click.echo(f"wrote {', '.join(names)} to {out}")


# ── bootstrap ────────────────────────────────────────────────────────────────


def _intervals_text(run: BootstrapRun) -> str:
    lines = []
    for which, title in (("rchi", "reduced chi2 closest to 1"), ("wrms", "minimum WRMS, ties included")):
        iv = run.intervals(which)
        lines.append(f"95% interval of the picks, {title}:")
        lines.append(f"  {'':6}{'2.5%':>10}{'median':>10}{'97.5%':>10}")
        for name, row in iv.iterrows():
            lines.append(f"  {name:<6}{row['low']:10.3f}{row['median']:10.3f}{row['high']:10.3f}")
    return "\n".join(lines) + "\n"


@group.command("bootstrap")
@_shared(grid_too=True)
@click.option("-o", "--out", type=click.Path(file_okay=False, path_type=Path), required=True,
              help="Output directory.")  # fmt: skip
@click.option("--samples", "n_samples", type=click.IntRange(min=1), help="How many resamples.")
@click.option("--sample-size", type=click.IntRange(min=1),
              help="Stations drawn per resample, with replacement.  [default: every station but the reference]")  # fmt: skip
@click.option("--seed", type=int, help="Seed for the resampling.  [default: a new one, recorded in settings.json]")
def bootstrap_cmd(velocities: Path, settings_file: Path | None, out: Path, overwrite: bool, **given: Any) -> None:
    """Resample the stations, fit the grid and pick, many times: bootstrap_v2.py.

    Writes parameters_rchi.txt (one pick per resample), parameters_wrms.txt
    (every model at the minimum WRMS, per resample), intervals.txt and
    settings.json. The settings include the seed, so
    `--settings <out>/settings.json` repeats the run exactly.

        pogf-modeling bootstrap PHm.csv --settings leyte_south.json --samples 1000 -o boot1/
    """
    merged = _merge(settings_file, given)
    prof, axes = _profile(merged), _grid(merged)
    sigma = _choice(merged, "sigma", ("legacy", "propagated"))
    drop = _choice(merged, "drop", ("first", "reference"))
    if "n_samples" not in merged:
        raise click.ClickException("the bootstrap needs --samples (or n_samples in --settings)")
    names = ["parameters_rchi.txt", "parameters_wrms.txt", "intervals.txt", SETTINGS_NAME]
    try:
        n_samples = int(merged["n_samples"])
        df = read_velocities(velocities)
        population, reference_row, reference = _split_reference(df, merged)
        sample_size = int(merged.get("sample_size") or len(population))
        seed = int(merged["seed"]) if merged.get("seed") is not None else secrets.randbits(32)
        if n_samples < 1 or sample_size < 1:
            raise ValueError("n_samples and sample_size must be at least 1")
        _out_dir(out, names, overwrite)
        click.echo(f"{n_samples} resamples of {sample_size} from {len(population)} stations, "
                   f"{axes.size:,} models each, seed {seed}", err=True)  # fmt: skip
        run = bootstrap(population, reference_row, prof, axes, n_samples=n_samples,
                        sample_size=sample_size, seed=seed, sigma=sigma, drop=drop)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from None
    (out / "parameters_rchi.txt").write_text("".join(pick_line(m) + "\n" for m in run.rchi_picks))
    (out / "parameters_wrms.txt").write_text(
        "".join(pick_line(m) + "\n" for ties in run.wrms_picks for m in ties)
    )
    intervals = _intervals_text(run)
    (out / "intervals.txt").write_text(intervals)
    record = _record(prof, axes, reference=reference, sigma=sigma, drop=drop,
                     n_samples=n_samples, sample_size=sample_size, seed=seed, velocities=str(velocities),
                     population_sha256=run.settings["population_sha256"],
                     reference_sha256=run.settings["reference_sha256"])  # fmt: skip
    (out / SETTINGS_NAME).write_text(json.dumps(record, indent=2) + "\n")
    click.echo(intervals, nl=False)
    click.echo(f"wrote {', '.join(names)} to {out}")


if __name__ == "__main__":
    group()
