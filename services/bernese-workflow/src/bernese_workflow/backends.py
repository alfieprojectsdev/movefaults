"""
BPE backend implementations for Bernese GNSS Software 5.4.

BPEBackend is a typing.Protocol — any class satisfying the three-method
interface is accepted without inheritance.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

_SUBDIRS = ("ATM", "BPE", "GRD", "OBS", "ORB", "ORX", "OUT", "RAW", "SOL", "STA")


@dataclass
class BPEResult:
    success: bool
    stations_survived: int | None          # count after PID 221/222 RXOBV3
    ambiguity_fixing_rate: float | None    # from PID 443 AMBXTR, 0.0-1.0
    helmchk_failed: bool                   # PID 513 reference station motion
    comparf_failed: bool                   # PID 514 daily repeatability
    output_files: dict[str, Path] = field(default_factory=dict)
    raw_log: str = ""


class BPEBackend(Protocol):
    def prepare_campaign(self, campaign_name: str, year: int, session: str, **kwargs: object) -> None: ...
    def run(self, campaign_name: str, year: int, session: str) -> BPEResult: ...
    def collect_outputs(self, campaign_name: str, year: int, session: str) -> dict[str, Path]: ...


def _parse_bpe_output(log_text: str) -> BPEResult:
    """
    Parse Bernese BPE stdout log into a BPEResult.

    Patterns are intentionally lenient — missing lines produce None/False
    rather than raising, because BPE logs vary across versions and failure
    modes may truncate output before quality-gate lines are emitted.
    """
    success = bool(re.search(r"BPE\s+finished", log_text, re.IGNORECASE))

    m = re.search(r"Stations\s+accepted\s*:\s*(\d+)", log_text, re.IGNORECASE)
    stations_survived = int(m.group(1)) if m else None

    ambiguity_fixing_rate: float | None = None
    m = re.search(r"Fixing\s+rate\s*:\s*([\d.]+)\s*%", log_text, re.IGNORECASE)
    if m:
        ambiguity_fixing_rate = float(m.group(1)) / 100.0
    else:
        m = re.search(r"Fixing\s+rate\s*:\s*([\d.]+)", log_text, re.IGNORECASE)
        if m:
            v = float(m.group(1))
            # Values > 1.0 are already in percentage form despite missing '%'
            ambiguity_fixing_rate = v / 100.0 if v > 1.0 else v

    helmchk_failed = bool(re.search(r"HELMCHK\s*:\s*failed", log_text, re.IGNORECASE))
    comparf_failed = bool(re.search(r"COMPARF\s*:\s*failed", log_text, re.IGNORECASE))

    return BPEResult(
        success=success,
        stations_survived=stations_survived,
        ambiguity_fixing_rate=ambiguity_fixing_rate,
        helmchk_failed=helmchk_failed,
        comparf_failed=comparf_failed,
        raw_log=log_text,
    )


class LinuxBPEBackend:
    """
    Invokes Bernese BPE via the Perl startBPE.pm API on Linux.

    bernese_root = $X  (Bernese install, e.g. ~/BERN54)
    user_dir     = $U  (user env dir,     e.g. ~/GPSUSER)
    campaign_dir = $P  (campaigns root,   e.g. ~/GPSDATA)
    """

    def __init__(
        self,
        bernese_root: str | Path,
        user_dir: str | Path,
        campaign_dir: str | Path,
        timeout_sec: int = 7200,
    ) -> None:
        self.bernese_root = Path(bernese_root).expanduser()
        self.user_dir = Path(user_dir).expanduser()
        self.campaign_dir = Path(campaign_dir).expanduser()
        self.timeout_sec = timeout_sec

    def prepare_campaign(self, campaign_name: str, year: int, session: str, **kwargs: object) -> None:
        campaign_path = self.campaign_dir / campaign_name
        for subdir in _SUBDIRS:
            (campaign_path / subdir).mkdir(parents=True, exist_ok=True)
        logger.info("Campaign directory prepared: %s", campaign_path)

    def run(self, campaign_name: str, year: int, session: str) -> BPEResult:
        script = self.user_dir / "SCRIPT" / "rnx2snx_pcs.pl"
        env_overrides = {
            "PCF_FILE": "RNX2SNX",
            "CPU_FILE": "PCF",
            "BPE_CAMPAIGN": campaign_name,
            "YEAR": str(year),
            "SESSION": session,
        }

        env = {**os.environ, **env_overrides}

        logger.info("Starting BPE: perl %s %s %s", script, year, session)
        try:
            proc = subprocess.run(
                ["perl", str(script), str(year), session],
                capture_output=True,
                text=True,
                env=env,
                timeout=self.timeout_sec,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"BPE timed out after {self.timeout_sec}s for campaign {campaign_name}"
            ) from exc

        combined = proc.stdout + "\n" + proc.stderr
        result = _parse_bpe_output(combined)
        result.output_files = self.collect_outputs(campaign_name, year, session)

        if not result.success:
            logger.error("BPE did not finish cleanly for %s. See raw_log.", campaign_name)
        else:
            logger.info(
                "BPE finished: stations=%s fixing_rate=%s helmchk_failed=%s",
                result.stations_survived,
                result.ambiguity_fixing_rate,
                result.helmchk_failed,
            )
        return result

    def collect_outputs(self, campaign_name: str, year: int, session: str) -> dict[str, Path]:
        out_dir = self.campaign_dir / campaign_name / "OUT"
        result: dict[str, Path] = {}
        snx = next(out_dir.glob("*.SNX"), None)
        nq0 = next(out_dir.glob("*.NQ0"), None)
        if snx:
            result["sinex"] = snx
        if nq0:
            result["nq0"] = nq0
        return result


class WindowsBPEBackend:
    """Windows BPE backend stub — satisfies BPEBackend Protocol, not yet implemented."""

    def prepare_campaign(self, campaign_name: str, year: int, session: str, **kwargs: object) -> None:
        raise NotImplementedError("WindowsBPEBackend is not yet implemented")

    def run(self, campaign_name: str, year: int, session: str) -> BPEResult:
        raise NotImplementedError("WindowsBPEBackend is not yet implemented")

    def collect_outputs(self, campaign_name: str, year: int, session: str) -> dict[str, Path]:
        raise NotImplementedError("WindowsBPEBackend is not yet implemented")
