from __future__ import annotations

import logging
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
