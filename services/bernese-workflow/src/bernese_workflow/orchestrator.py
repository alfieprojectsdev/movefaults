from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jinja2

if TYPE_CHECKING:
    from .backends import BPEBackend, BPEResult

logger = logging.getLogger(__name__)


class BerneseOrchestrator:
    def __init__(
        self,
        bernese_path: str,
        template_dir: str,
        backend: BPEBackend | None = None,
        user_dir: str | Path | None = None,
        campaign_dir: str | Path | None = None,
    ) -> None:
        self.bernese_path = bernese_path
        self.template_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_dir),
            keep_trailing_newline=True,
            undefined=jinja2.StrictUndefined,
        )
        if backend is None:
            from .backends import LinuxBPEBackend

            self._backend: BPEBackend = LinuxBPEBackend(
                bernese_root=bernese_path,
                user_dir=user_dir if user_dir is not None else Path(bernese_path) / "GPSUSER",
                campaign_dir=campaign_dir if campaign_dir is not None else Path(bernese_path) / "GPSDATA",
            )
        else:
            self._backend = backend

    def generate_pcf(self, template_name: str, context: dict[str, Any], output_path: str) -> None:
        """Render a Jinja2 PCF template and write to output_path."""
        template = self.template_env.get_template(template_name)
        content = template.render(context)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("Generated PCF file: %s", output_path)

    def run_bpe(self, campaign_name: str, year: int, session: str) -> BPEResult:
        """Execute a Bernese BPE run via the configured backend."""
        logger.info("Starting BPE run: campaign=%s year=%s session=%s", campaign_name, year, session)
        return self._backend.run(campaign_name, year, session)

    def run_velocity_pipeline(
        self,
        reference_station: str,
        *,
        crd_dir: str | Path,
        runx_script: str | Path,
    ) -> None:
        """Run the post-BPE velocity pipeline (RUNX_v2.py) headlessly.

        Args:
            reference_station: 4-char station code used as the ENU coordinate origin.
            crd_dir:           Directory containing the daily *.CRD files to process.
                               RUNX_v2.py globs '*.CRD' from its working directory.
            runx_script:       Absolute path to RUNX_v2.py
                               (analysis/02 Time Series/RUNX_v2.py in the monorepo).

        Raises:
            FileNotFoundError: if runx_script does not exist.
            RuntimeError: if the script exits with a non-zero return code.
        """
        crd_dir = Path(crd_dir)
        runx_script = Path(runx_script)

        if not runx_script.is_file():
            raise FileNotFoundError(f"RUNX_v2 script not found: {runx_script}")

        logger.info(
            "Running velocity pipeline: ref=%s crd_dir=%s", reference_station, crd_dir
        )
        proc = subprocess.run(
            [sys.executable, str(runx_script), "--reference-station", reference_station],
            cwd=crd_dir,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"RUNX_v2 velocity pipeline failed (exit {proc.returncode}):\n"
                f"{proc.stderr or proc.stdout}"
            )
        logger.info("Velocity pipeline complete. stdout:\n%s", proc.stdout)
