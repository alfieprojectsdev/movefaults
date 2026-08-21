"""
RINEX Quality Control using teqc.

teqc is the UNAVCO standard QC tool for RINEX 2 observation files.
Install: https://www.unavco.org/software/data-processing/teqc/teqc.html
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import click


class QCToolUnavailableError(RuntimeError):
    """No usable QC binary is installed.

    Distinct from "the tool ran and failed": nothing was executed, so nothing
    is known about the file. Callers that treat QC as optional enrichment
    (the ingestion pipeline does) may degrade to null metrics on this and only
    this; every other failure still means something went wrong with the data.

    Subclasses RuntimeError so pre-existing ``except RuntimeError`` handlers
    keep working unchanged.
    """


class QCToolTimeoutError(RuntimeError):
    """A QC binary was found and started, but exceeded ``timeout_sec``."""


@dataclass
class RINEXQCResult:
    """Structured output from a teqc +qc run."""
    obs_count: int | None          # total observations across all types
    cycle_slips: int | None        # number of cycle slips detected
    mp1_rms: float | None          # L1 multipath RMS in metres
    mp2_rms: float | None          # L2 multipath RMS in metres
    raw_output: str                # full tool output for debugging
    # Which tool produced this, and why. A result that does not say which
    # binary made it cannot be reproduced later -- see the provenance note in
    # docs/project_documentation/gfzrnx_vs_teqc_rinex3_evidence.md.
    tool: str = "teqc"             # "teqc" | "gfzrnx"
    fallback_reason: str | None = None  # set when teqc was tried and refused


def _parse_teqc_output(text: str) -> RINEXQCResult:
    """Parse teqc summary text into a RINEXQCResult.

    Handles minor format variation across teqc versions by using
    flexible whitespace in all patterns.
    """
    def _first_int(pattern: str) -> int | None:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            # first contiguous digit run handles multi-column rows like "85321  84000  ..."
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

    # PRIMARY: the SUM row, which is where teqc 2019Feb25 actually puts these.
    #
    #   first epoch    last epoch    hrs   dt  #expt  #have   %   mp1   mp2 o/slps
    #   SUM 25 5 1 00:00 25 5 1 23:59 24.00 30    -   46370   -  0.74  0.49    284
    #
    # Indexed from the RIGHT because the leading epoch fields vary in width
    # between versions and configurations, while the trailing metrics do not.
    # The earlier `key : value` patterns below never matched this format; the
    # mismatch stayed invisible for as long as teqc was not installed here.
    obs_count = cycle_slips = None
    mp1_rms = mp2_rms = None
    for line in text.splitlines():
        if not line.startswith("SUM "):
            continue
        tok = line.split()
        if len(tok) < 8:
            continue

        def _num(t: str):
            try:
                return float(t)
            except ValueError:
                return None  # teqc writes '-' for unavailable columns

        slips = _num(tok[-1])
        m2, m1 = _num(tok[-2]), _num(tok[-3])
        have = _num(tok[-5])
        cycle_slips = int(slips) if slips is not None else None
        mp2_rms, mp1_rms = m2, m1
        obs_count = int(have) if have is not None else None
        break

    # FALLBACK: `key : value` forms from other teqc versions.
    if obs_count is None:
        obs_count = _first_int(r'#\s*obs\s*:\s*([0-9 ]+)')
    if obs_count is None:
        obs_count = _first_int(r'total\s+obs\s*:\s*([0-9 ]+)')
    if cycle_slips is None:
        cycle_slips = _first_int(r'#?\s*slips[^:]*:\s*([0-9 ]+)')
    if mp1_rms is None:
        mp1_rms = _first_float(r'MP1\s*:\s*([\d.]+)')
    if mp2_rms is None:
        mp2_rms = _first_float(r'MP2\s*:\s*([\d.]+)')

    return RINEXQCResult(
        obs_count=obs_count,
        cycle_slips=cycle_slips,
        mp1_rms=mp1_rms,
        mp2_rms=mp2_rms,
        raw_output=text,
    )


# teqc refuses RINEX 3 on line 1 with a specific, stable message. Matching the
# message rather than sniffing the file version keeps the trigger tied to the
# actual failure: if a future teqc gains RINEX 3 support, this stops firing on
# its own instead of routing around a tool that now works.
_TEQC_RINEX3_REFUSAL = re.compile(
    r"unaccepted RINEX version|must be RINEX Version <= 2\.11", re.I
)


def _parse_gfzrnx_output(text: str) -> RINEXQCResult:
    """Parse `gfzrnx -stk_obs` output.

    gfzrnx reports per-satellite observation counts in STO rows rather than
    teqc's summary block, so the two tools do NOT report the same quantities:

      obs_count    summed across all STO rows -- comparable in spirit to
                   teqc's total, but not identical in definition
      cycle_slips  NOT reported by -stk_obs; left None rather than guessed
      mp1/mp2_rms  NOT reported by -stk_obs; left None

    Leaving fields None is deliberate. A number that looks like teqc's but
    means something else is worse than an absent one, because it will be
    compared against teqc results without anyone noticing the difference.
    """
    total = 0
    seen = False
    for line in text.splitlines():
        parts = line.split()
        if len(parts) > 4 and parts[0] == "STO":
            for tok in parts[3:]:
                if tok.isdigit():
                    total += int(tok)
                    seen = True
    return RINEXQCResult(
        obs_count=total if seen else None,
        cycle_slips=None,
        mp1_rms=None,
        mp2_rms=None,
        raw_output=text,
        tool="gfzrnx",
    )


class RinexQC:
    """RINEX quality control, teqc-first with a gfzrnx fallback.

    **teqc is primary by choice, not by accident.** It is the more heavily
    exercised of the two here and its output format is what everything
    downstream parses. But teqc was discontinued in 2019 and cannot read
    RINEX 3 *at all* -- it refuses on line 1 -- while every IGS fiducial this
    project uses is RINEX 3. Without a fallback the QC step is silently blind
    to exactly the stations that tie the network to the reference frame.

    So: run teqc; if and only if it refuses the file for being RINEX 3, retry
    with gfzrnx and record that it happened. Any other teqc failure still
    raises, because "teqc broke" and "teqc cannot read this format" are
    different problems and only one of them has a safe automatic answer.

    LICENCE/PROVENANCE: gfzrnx's free licence covers research use;
    operational pipeline use needs a commercial licence. Per the direction of
    2026-08-12 this is not a blocker, but every result carries `tool` so that
    actual usage is recoverable from the record rather than from memory.
    """

    def __init__(
        self,
        teqc_path: str = "teqc",
        timeout_sec: int = 120,
        gfzrnx_path: str | None = None,
        allow_fallback: bool = True,
    ):
        self.teqc_path = teqc_path
        self.timeout_sec = timeout_sec
        # Default resolves from PATH; the R740 keeps it outside PATH at
        # /home/gps3/gfzrnx/gfzrnx_2.2.0_lx64, so callers there must pass it.
        self.gfzrnx_path = gfzrnx_path or os.environ.get("GFZRNX_BIN", "gfzrnx")
        self.allow_fallback = allow_fallback

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
                # teqc absent entirely. Distinct from "teqc refused the
                # format", and recorded as a distinct fallback_reason so the
                # two never blur together in the provenance record.
                #
                # Falling back here is a judgement call: it makes QC work on a
                # machine with no teqc (the R740, as of 2026-08-13) instead of
                # failing outright. The cost is that a broken teqc install
                # looks like success unless someone reads `tool`. That is why
                # `tool` exists.
                if self.allow_fallback:
                    return self._run_gfzrnx(
                        path, reason=f"teqc not installed at '{self.teqc_path}'"
                    )
                raise QCToolUnavailableError(
                    f"teqc not found at '{self.teqc_path}' and fallback is "
                    "disabled. Install teqc, or enable the gfzrnx fallback. "
                    "Note teqc was discontinued in 2019 and cannot read RINEX 3."
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise QCToolTimeoutError(
                    f"teqc timed out after {self.timeout_sec}s for '{rinex_file}'"
                ) from exc

            combined = proc.stdout + "\n" + proc.stderr

            # teqc cannot read RINEX 3 and says so explicitly. That is the ONLY
            # condition that routes to gfzrnx; every other failure still raises,
            # because a broken teqc and an unsupported format need different
            # responses and only the latter has a safe automatic one.
            if _TEQC_RINEX3_REFUSAL.search(combined):
                if not self.allow_fallback:
                    raise RuntimeError(
                        f"teqc cannot read '{rinex_file}' (RINEX 3) and fallback "
                        "is disabled. Enable it, or QC this file with gfzrnx."
                    )
                return self._run_gfzrnx(
                    path,
                    reason="teqc refused the file as RINEX >2.11",
                )

            if proc.returncode not in (0, 1):  # teqc exits 1 on non-fatal warnings
                raise RuntimeError(
                    f"teqc exited {proc.returncode}: {proc.stderr[:500]}"
                )

            # teqc names its summary <basename>.<yy>S -- ALAB1210.25o yields
            # ALAB1210.25S, NOT ALAB1210.S. Looking for stem + ".S" never
            # matched, so this silently fell through to stdout, which carries
            # the ASCII sky plot rather than the SUM line the parser needs.
            # Verified 2026-08-13 against teqc 2019Feb25 on real data; the bug
            # was invisible until teqc was actually installed on this machine.
            summary_file = next(
                (c for c in (
                    tmp_path / (tmp_file.name.rsplit(".", 1)[0] + "." +
                                tmp_file.suffix.lstrip(".")[:2] + "S"),
                    tmp_path / (tmp_file.stem + ".S"),
                ) if c.exists()),
                None,
            )
            if summary_file is None:
                # Last resort: any .*S teqc left behind.
                found = sorted(tmp_path.glob("*S"))
                summary_file = found[0] if found else None

            if summary_file is not None:
                text = summary_file.read_text(errors="replace")
            else:
                text = proc.stdout + "\n" + proc.stderr

        return _parse_teqc_output(text)

    def _run_gfzrnx(self, path: Path, reason: str) -> RINEXQCResult:
        """QC a file with gfzrnx. Only reached when teqc refuses the format."""
        try:
            proc = subprocess.run(
                [self.gfzrnx_path, "-finp", str(path), "-stk_obs"],
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
            )
        except FileNotFoundError as exc:
            raise QCToolUnavailableError(
                f"teqc could not read '{path}' ({reason}) and the gfzrnx "
                f"fallback is not available at '{self.gfzrnx_path}'. "
                "Set GFZRNX_BIN or pass gfzrnx_path. On the R740 it is at "
                "/home/gps3/gfzrnx/gfzrnx_2.2.0_lx64."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise QCToolTimeoutError(
                f"gfzrnx timed out after {self.timeout_sec}s for '{path}'"
            ) from exc

        if proc.returncode != 0:
            raise RuntimeError(
                f"gfzrnx exited {proc.returncode} for '{path}': {proc.stderr[:500]}"
            )

        result = _parse_gfzrnx_output(proc.stdout + "\n" + proc.stderr)
        result.fallback_reason = reason
        return result


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
