"""
`crd-to-plots` — the console entry point the ported pipeline never had.

`crd_pipeline` and `analysis.py` between them reproduce the whole legacy
chain, verified against PHIVOLCS' MATLAB output. But there was no way to *run*
them: no CLI, no PLOT writer, no network filter. So `RUNX_v2.py` stayed in
production and the ported library sat unused.

This is that missing command.

`pogf-timeseries` groups the timeseries commands: `plots` is this same command
(so `crd-to-plots` keeps working unchanged), and `status` prints the read-only
JSON status of one station (`status.py`). `velocities` fits a whole PLOT
directory and writes the MATLAB's velocity table and outliers file
(`velocities.py`); `compare-velocities` checks one such table against another.
"""
from __future__ import annotations

import json
from pathlib import Path

import click

from . import gmt
from .offsets_catalog import load_offsets_catalog
from .plots import available_networks, crd_directory_to_plots, load_network
from .status import OutlierMode, station_status
from .velocities import (
    MANIFEST_NAME,
    OUTLIERS_NAME,
    TABLE_NAME,
    compare_velocity_tables,
    compute_velocities,
    format_outliers,
    format_velocity_table,
    read_site_list,
    write_manifest,
)


@click.command()
@click.argument(
    "crd_dir",
    required=False,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--reference", "-r", default=None,
    help="4-char station code used as the ENU origin. Was an input() prompt in RUNX_v2.py.",
)
@click.option(
    "--network", "-n", default="NP", show_default=True,
    help="Network definition from networks.yml; replaces the 00_CRD_*.bat scripts.",
)
@click.option(
    "--out", "-o", "out_dir", default=None, type=click.Path(file_okay=False, path_type=Path),
    help="Output directory for PLOT files [default: <crd_dir>/PLOTS].",
)
@click.option("--list-networks", is_flag=True, help="List the available networks and exit.")
def main(
    crd_dir: Path | None,
    reference: str,
    network: str,
    out_dir: Path | None,
    list_networks: bool,
) -> None:
    """Convert Bernese CRD files to per-site PLOT time series.

    Runs the whole legacy chain -- network filter, XYZ extraction, ENU
    transform, PLOT files -- in one command:

        crd-to-plots $S/LUZON/2025/SOL -r PIMO -n PIVS
    """
    if list_networks:
        for name in available_networks():
            net = load_network(name)
            click.echo(f"{name:8s} {len(net.exclusions):4d} excluded  {net.description}")
        return

    # Only required once we are actually going to process something --
    # --list-networks has to work without a campaign directory to hand.
    if crd_dir is None:
        raise click.UsageError("CRD_DIR is required unless --list-networks is given.")
    if not reference:
        raise click.UsageError("--reference/-r is required.")

    target = out_dir or (crd_dir / "PLOTS")
    try:
        written = crd_directory_to_plots(crd_dir, target, reference, network)
    except (KeyError, ValueError) as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc

    net = load_network(network)
    click.echo(f"network   : {net.name} ({len(net.exclusions)} stations excluded)")
    click.echo(f"reference : {reference.upper()}")
    click.echo(f"written   : {len(written)} PLOT files -> {target}")
    for station, path in sorted(written.items()):
        n = sum(1 for _ in path.open(encoding="utf-8"))
        click.echo(f"  {station}  {n:5d} epochs")


@click.group()
def group() -> None:
    """GNSS time series: PLOT files and read-only station status."""


group.add_command(main, name="plots")


@group.command()
@click.argument("crd_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--station", "-s", required=True, help="4-char station code.")
@click.option("--reference", "-r", required=True, help="4-char ENU origin station.")
@click.option(
    "--offsets", "offsets_catalog", default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="The `offsets` catalog. Without it the series is fitted as one segment.",
)
@click.option(
    "--outlier-mode", default=OutlierMode.RECORD.value, show_default=True,
    type=click.Choice([m.value for m in OutlierMode]),
    help="record: flag only, keep in the fit. exclude: leave flagged epochs out of the fit.",
)
@click.option("--iqr-factor", default=3.0, show_default=True, type=float,
              help="IQR multiplier of the outlier rule.")
@click.option("--indent", default=None, type=int, help="Pretty-print with this indent.")
def status(
    crd_dir: Path,
    station: str,
    reference: str,
    offsets_catalog: Path | None,
    outlier_mode: str,
    iqr_factor: float,
    indent: int | None,
) -> None:
    """Print one station's ENU series, offsets, velocity and outlier flags as JSON.

    Read-only: nothing is written. Outliers are flagged and, by default, kept
    in the fit.

        pogf-timeseries status $S/PHREF/2025/SOL -s ABCD -r WXYZ --offsets offsets
    """
    try:
        result = station_status(
            crd_dir, station, reference,
            offsets_catalog=offsets_catalog,
            outlier_mode=outlier_mode,
            outlier_iqr_factor=iqr_factor,
        )
    except (ValueError, OSError) as exc:  # OSError: an unreadable CRD or catalog
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc
    # allow_nan=False: NaN is not JSON, and a browser's JSON.parse rejects it.
    click.echo(json.dumps(result, indent=indent, allow_nan=False))


if __name__ == "__main__":
    main()


@group.command()
@click.argument("plot_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--offsets", "offsets_catalog", default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="The `offsets` catalog [default: PLOT_DIR/offsets if present].",
)
@click.option(
    "--no-offsets", is_flag=True,
    help="Fit every series as one segment. Required to run without a catalog, "
         "so a missing catalog is never silent.",
)
@click.option("--sites", "site_list", default=None,
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="Site list [default: PLOT_DIR/123].")
@click.option(
    "--outlier-mode", default=OutlierMode.RECORD.value, show_default=True,
    type=click.Choice([m.value for m in OutlierMode]),
    help="record: flag only, keep in the fit, as the MATLAB does. "
         "exclude: leave flagged epochs out of the fit.",
)
@click.option("--iqr-factor", default=3.0, show_default=True, type=float,
              help="IQR multiplier of the outlier rule.")
@click.option("--out", "-o", "out_dir", default=None,
              type=click.Path(file_okay=False, path_type=Path),
              help="Output directory [default: PLOT_DIR].")
@click.option("--reference", "-r", default=None,
              help="The series' ENU origin station. Recorded in the manifest; "
                   "required with --crd.")
@click.option(
    "--crd", "crd_file", default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="One CRD file for station positions. With it, also write velocities.psvelo.",
)
def velocities(
    plot_dir: Path,
    offsets_catalog: Path | None,
    no_offsets: bool,
    site_list: Path | None,
    outlier_mode: str,
    iqr_factor: float,
    out_dir: Path | None,
    reference: str | None,
    crd_file: Path | None,
) -> None:
    """Fit every site in a PLOT directory; write the MATLAB's two output files.

    Writes `Velocity_rover(regress)_10` and `outliers` in the layout of
    vel_line_v8_newvelduetooffset_v4.m, plus velocities_manifest.json recording
    the catalog's checksum and the settings. The default outlier mode, record,
    reproduces the MATLAB's numbers.

        pogf-timeseries velocities PLOTS/ --offsets offsets
        pogf-timeseries velocities PLOTS/ --offsets offsets --crd FIN.CRD -r PIMO
    """
    if offsets_catalog and no_offsets:
        raise click.UsageError("--offsets and --no-offsets contradict each other.")
    if offsets_catalog is None and not no_offsets:
        default = plot_dir / "offsets"
        if not default.is_file():
            raise click.UsageError(
                f"No offsets catalog: pass --offsets, put one at {default}, "
                "or pass --no-offsets to fit each series as one segment."
            )
        offsets_catalog = default
    if crd_file and not reference:
        raise click.UsageError("--crd needs --reference: a velocity map must say "
                               "what its velocities are relative to.")
    site_list = site_list or plot_dir / "123"
    if not site_list.is_file():
        raise click.UsageError(f"No site list at {site_list}; pass --sites.")
    out_dir = out_dir or plot_dir

    try:
        catalog = load_offsets_catalog(offsets_catalog) if offsets_catalog else {}
        sites = read_site_list(site_list)
    except (ValueError, OSError) as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc

    results, failures = compute_velocities(
        plot_dir, sites, catalog,
        exclude_outliers=outlier_mode == OutlierMode.EXCLUDE.value,
        iqr_factor=iqr_factor,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    table = out_dir / TABLE_NAME
    outliers = out_dir / OUTLIERS_NAME
    table.write_text(format_velocity_table(results), encoding="utf-8")
    outliers.write_text(format_outliers(results), encoding="utf-8")
    written = [table, outliers]

    if crd_file:
        vectors, missing = gmt.to_vectors(
            [r for _, r in results], gmt.station_positions(crd_file),
        )
        psvelo = out_dir / "velocities.psvelo"
        n, withheld = gmt.write_psvelo(
            vectors, psvelo, reference_station=reference.upper(),
            withhold=gmt.short_final_interval(vectors),
        )
        written.append(psvelo)
        click.echo(f"psvelo    : {n} drawn, {len(withheld)} withheld -> {psvelo}")
        if missing:
            click.echo(f"  no position in {crd_file.name}: {' '.join(missing)}", err=True)

    write_manifest(
        out_dir / MANIFEST_NAME,
        plot_dir=plot_dir, site_list=site_list, offsets=offsets_catalog,
        outlier_mode=outlier_mode, iqr_factor=iqr_factor, reference=reference,
        n_sites=len(sites), failures=failures, written=written,
    )
    click.echo(f"catalog   : {offsets_catalog or 'none (--no-offsets)'}")
    click.echo(f"outliers  : {outlier_mode}")
    click.echo(f"fitted    : {len(results)} of {len(sites)} sites -> {table}")
    for f in failures:
        click.echo(f"  NOT FITTED {f.site}: {f.reason}", err=True)


@group.command("compare-velocities")
@click.argument("ours", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("theirs", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def compare_velocities(ours: Path, theirs: Path) -> None:
    """Compare two Velocity_rover tables, site by site and segment by segment.

    "match" means every value prints the same at the table's own precision
    (velocities to 5 decimals, sigmas to 1). Exits 1 if any site differs.

        pogf-timeseries compare-velocities PLOTS/'Velocity_rover(regress)_10' matlab_run.txt
    """
    rows = compare_velocity_tables(ours, theirs)
    for r in rows:
        if r.status in ("match", "differ"):
            click.echo(f"{r.site:<6} {r.status:<11} velocity {r.worst_velocity:.6f} mm/yr"
                       f"  sigma {r.worst_sigma:.2f}")
        else:
            click.echo(f"{r.site:<6} {r.status:<11} {r.detail}")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
    click.echo("summary: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    if any(r.status != "match" for r in rows):
        raise SystemExit(1)
