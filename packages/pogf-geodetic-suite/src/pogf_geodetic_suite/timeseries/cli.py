"""
`crd-to-plots` — the console entry point the ported pipeline never had.

`crd_pipeline` and `analysis.py` between them reproduce the whole legacy
chain, verified against PHIVOLCS' MATLAB output. But there was no way to *run*
them: no CLI, no PLOT writer, no network filter. So `RUNX_v2.py` stayed in
production and the ported library sat unused.

This is that missing command.
"""
from __future__ import annotations

from pathlib import Path

import click

from .plots import available_networks, crd_directory_to_plots, load_network


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


if __name__ == "__main__":
    main()
