"""
RINEX Quality Control using teqc.

teqc is the UNAVCO standard QC tool for RINEX 2 observation files.
Install: https://www.unavco.org/software/data-processing/teqc/teqc.html
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import click


@dataclass
class RINEXQCResult:
    """Structured output from a teqc +qc run."""
    obs_count: int | None          # total observations across all types
    cycle_slips: int | None        # number of cycle slips detected
    mp1_rms: float | None          # L1 multipath RMS in metres
    mp2_rms: float | None          # L2 multipath RMS in metres
    raw_output: str                # full teqc output for debugging


def _parse_teqc_output(text: str) -> RINEXQCResult:
    """Parse teqc summary text into a RINEXQCResult.

    Handles minor format variation across teqc versions by using
    flexible whitespace in all patterns.
    """
    def _first_int(pattern: str) -> int | None:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            # grab the first run of digits in the captured group
            digits = re.search(r'\d+', m.group(1))
            return int(digits.group()) if digits else None
        return None

    def _first_float(pattern: str) -> float | None:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1).strip())
            except ValueError:
                return None
        return None

    obs_count   = _first_int(r'#\s*obs\s*:\s*([0-9 ]+)')
    if obs_count is None:
        obs_count = _first_int(r'total\s+obs\s*:\s*([0-9 ]+)')

    cycle_slips = _first_int(r'#?\s*slips[^:]*:\s*([0-9 ]+)')
    mp1_rms     = _first_float(r'MP1\s*:\s*([\d.]+)')
    mp2_rms     = _first_float(r'MP2\s*:\s*([\d.]+)')

    return RINEXQCResult(
        obs_count=obs_count,
        cycle_slips=cycle_slips,
        mp1_rms=mp1_rms,
        mp2_rms=mp2_rms,
        raw_output=text,
    )


class RinexQC:
    def __init__(self, teqc_path: str = "teqc", timeout_sec: int = 120):
        self.teqc_path = teqc_path
        self.timeout_sec = timeout_sec

    def run_qc(self, rinex_file: str) -> RINEXQCResult:
        """Run teqc +qc on a RINEX file and return structured results.

        Raises FileNotFoundError if the RINEX file does not exist.
        Raises RuntimeError if teqc exits with a non-zero status or times out.
        Returns a RINEXQCResult with None fields when teqc output does not
        contain recognisable values (e.g. very old teqc version).
        """
        path = Path(rinex_file)
        if not path.exists():
            raise FileNotFoundError(f"RINEX file not found: {rinex_file}")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Copy file into temp dir so .S output lands there
            tmp_file = tmp_path / path.name
            shutil.copy2(path, tmp_file)

            try:
                proc = subprocess.run(
                    [self.teqc_path, "+qc", str(tmp_file)],
                    capture_output=True,
                    text=True,
                    cwd=tmp,
                    timeout=self.timeout_sec,
                )
            except FileNotFoundError as exc:
                raise RuntimeError(
                    f"teqc not found at '{self.teqc_path}'. "
                    "Install from https://www.unavco.org/software/data-processing/teqc/teqc.html"
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    f"teqc timed out after {self.timeout_sec}s for '{rinex_file}'"
                ) from exc

            if proc.returncode not in (0, 1):  # teqc exits 1 on non-fatal warnings
                raise RuntimeError(
                    f"teqc exited {proc.returncode}: {proc.stderr[:500]}"
                )

            # Prefer the .S summary file; fall back to combined stdout+stderr
            summary_file = tmp_path / (tmp_file.stem + ".S")
            if summary_file.exists():
                text = summary_file.read_text(errors="replace")
            else:
                text = proc.stdout + "\n" + proc.stderr

        return _parse_teqc_output(text)


@click.command()
@click.option("--file", "-f", required=True, type=click.Path(exists=True), help="Path to RINEX file")
@click.option("--bin", "teqc_bin", default="teqc", help="Path to teqc binary")
def main(file: str, teqc_bin: str):
    """RINEX Quality Control using teqc."""
    qc = RinexQC(teqc_bin)
    try:
        result = qc.run_qc(file)
        click.echo(f"Observations : {result.obs_count}")
        click.echo(f"Cycle slips  : {result.cycle_slips}")
        click.echo(f"MP1 RMS (m)  : {result.mp1_rms}")
        click.echo(f"MP2 RMS (m)  : {result.mp2_rms}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
