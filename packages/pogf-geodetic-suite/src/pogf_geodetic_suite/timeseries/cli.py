"""
`crd-to-plots` — the console entry point the ported pipeline never had.

`crd_pipeline` and `analysis.py` between them reproduce the whole legacy
chain, verified against PHIVOLCS' MATLAB output. But there was no way to *run*
them: no CLI, no PLOT writer, no network filter. So `RUNX_v2.py` stayed in
production and the ported library sat unused.

This is that missing command.

`pogf-timeseries` groups the timeseries commands: `plots` is this same command
(so `crd-to-plots` keeps working unchanged), and `status` prints the read-only
JSON status of one station (`status.py`).
"""
from __future__ import annotations

import json
from pathlib import Path

import click

from .plots import available_networks, crd_directory_to_plots, load_network
from .status import OutlierMode, station_status


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
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc
    # allow_nan=False: NaN is not JSON, and a browser's JSON.parse rejects it.
    click.echo(json.dumps(result, indent=indent, allow_nan=False))


if __name__ == "__main__":
    main()
