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
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .campaign_models import CampaignConfig

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

    def prepare_campaign(
        self,
        campaign_name: str,
        year: int,
        session: str,
        config: CampaignConfig | None = None,
        **kwargs: object,
    ) -> None:
        """Create campaign subdirectories and, if *config* is provided,
        generate Bernese input files (STA, CRD, ABB, VEL, CLU, BLQ).

        File generation order: subdirs → STA → CRD → ABB → VEL → CLU → BLQ.
        BLQ download is skipped when config.download_blq is False.
        """
        from .campaign_builder import (
            generate_abb,
            generate_clu,
            generate_crd,
            generate_sta,
            generate_vel,
            stage_atx,
        )

        campaign_path = self.campaign_dir / campaign_name
        for subdir in _SUBDIRS:
            (campaign_path / subdir).mkdir(parents=True, exist_ok=True)
        logger.info("Campaign subdirs created: %s", campaign_path)

        if config is None:
            return

        sta_dir = campaign_path / "STA"

        # 1. STA
        (sta_dir / f"{campaign_name}.STA").write_text(
            generate_sta(config.stations), encoding="ascii"
        )
        # 2+3. CRD + ABB
        (sta_dir / f"{campaign_name}.CRD").write_text(
            generate_crd(config.stations, ref_frame=config.ref_frame, epoch=config.epoch),
            encoding="ascii",
        )
        (sta_dir / f"{campaign_name}.ABB").write_text(
            generate_abb(config.stations), encoding="ascii"
        )
        # 4. ATX staging (ATM/)
        if config.atx_source is not None:
            stage_atx(Path(config.atx_source), campaign_path / "ATM")
        # 5. VEL
        (sta_dir / f"{campaign_name}.VEL").write_text(
            generate_vel(config.stations, ref_frame=config.ref_frame),
            encoding="ascii",
        )
        # 6. CLU
        (sta_dir / f"{campaign_name}.CLU").write_text(
            generate_clu(config.stations), encoding="ascii"
        )
        # 7. BLQ
        if config.download_blq:
            from .campaign_builder import download_blq
            download_blq(
                config.stations,
                sta_dir / f"{campaign_name}.BLQ",
                model=config.blq_model,
            )

        logger.info("Campaign files generated in %s", sta_dir)

    def run(self, campaign_name: str, year: int, session: str) -> BPEResult:
        from .rinex_header_validator import ValidationError, validate_rinex_headers

        campaign_path = self.campaign_dir / campaign_name
        raw_dir = campaign_path / "RAW"
        sta_path = campaign_path / "STA" / f"{campaign_name}.STA"

        if raw_dir.exists() and sta_path.exists():
            atm_dir = campaign_path / "ATM"
            if atm_dir.exists():
                # resolve() deduplicates on case-insensitive filesystems (e.g. macOS)
                # where *.atx and *.ATX would otherwise match the same file twice.
                seen: dict[Path, Path] = {}
                for p in list(atm_dir.glob("*.atx")) + list(atm_dir.glob("*.ATX")):
                    seen.setdefault(p.resolve(), p)
                atx_candidates = sorted(seen.values())
            else:
                atx_candidates = []

            if len(atx_candidates) == 1:
                atx_path: Path | None = atx_candidates[0]
            elif len(atx_candidates) > 1:
                logger.warning(
                    "Multiple ATX files found in %s — skipping ATX coverage check. "
                    "Remove stale files to enable ATX validation: %s",
                    atm_dir,
                    [p.name for p in atx_candidates],
                )
                atx_path = None
            else:
                atx_path = None

            report = validate_rinex_headers(raw_dir, sta_path, atx_path=atx_path)
            if not report.ok:
                raise ValidationError(report)
        else:
            logger.warning(
                "Pre-flight RINEX header check skipped for %s (RAW/ or STA not present)",
                campaign_name,
            )

        script = self.user_dir / "SCRIPT" / "rnx2snx_pcs.pl"
        env_overrides = {
            # Bernese path variables required by Perl scripts
            "X": str(self.bernese_root),
            "U": str(self.user_dir),
            "P": str(self.campaign_dir),
            # BPE session parameters
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

    def run_continuous(self, campaign_name: str, year: int, session: str) -> tuple[BPEResult, BPEResult]:
        """Two-pass BPE for continuous GPS campaigns.

        Pass 1: standard BPE run (float + fixed solution).
        Pass 2: BPE run using the output CRD from pass 1 as the a priori
                coordinate file, replacing the campaign CRD before re-running.

        Returns a tuple of (pass1_result, pass2_result).  Raises if pass 1
        does not succeed (no point running pass 2 with bad a priori coords).
        """
        logger.info("Continuous GPS: starting pass 1 for %s", campaign_name)
        result1 = self.run(campaign_name, year, session)

        if not result1.success:
            raise RuntimeError(
                f"Continuous GPS pass 1 failed for {campaign_name}; "
                "aborting pass 2.  Check raw_log on the returned BPEResult."
            )

        # Promote the pass-1 output CRD → input CRD for pass 2
        sta_dir = self.campaign_dir / campaign_name / "STA"
        snx_path = result1.output_files.get("sinex")
        if snx_path is None:
            raise RuntimeError(
                f"Continuous GPS pass 1 produced no SINEX for {campaign_name}; "
                "cannot seed pass 2."
            )

        # Bernese writes the final coordinates to OUT/*.CRD as well (FIN_*.CRD).
        # Look for it and overwrite the STA CRD so pass 2 uses updated coords.
        out_dir = self.campaign_dir / campaign_name / "OUT"
        crd_candidates = sorted(out_dir.glob("FIN_*.CRD"))
        if crd_candidates:
            import shutil
            dest_crd = sta_dir / f"{campaign_name}.CRD"
            shutil.copy2(crd_candidates[-1], dest_crd)
            logger.info("Pass-2 seed CRD: %s → %s", crd_candidates[-1], dest_crd)
        else:
            logger.warning("No FIN_*.CRD found in OUT/; pass 2 will reuse the original CRD")

        logger.info("Continuous GPS: starting pass 2 for %s", campaign_name)
        result2 = self.run(campaign_name, year, session)
        return result1, result2

    def collect_outputs(self, campaign_name: str, year: int, session: str) -> dict[str, Path]:
        out_dir = self.campaign_dir / campaign_name / "OUT"
        result: dict[str, Path] = {}

        for key, suffix in (("sinex", "*.SNX"), ("nq0", "*.NQ0")):
            matches = sorted(out_dir.glob(suffix))
            if len(matches) == 1:
                result[key] = matches[0]
            elif len(matches) > 1:
                raise RuntimeError(
                    f"Ambiguous {suffix} outputs for campaign {campaign_name!r} "
                    f"(year={year}, session={session}): found {[str(m) for m in matches]}. "
                    "Clean the OUT/ directory before collecting outputs."
                )

        return result


class WindowsBPEBackend:
    """Windows BPE backend stub — satisfies BPEBackend Protocol, not yet implemented."""

    def prepare_campaign(self, campaign_name: str, year: int, session: str, **kwargs: object) -> None:
        raise NotImplementedError("WindowsBPEBackend is not yet implemented")

    def run(self, campaign_name: str, year: int, session: str) -> BPEResult:
        raise NotImplementedError("WindowsBPEBackend is not yet implemented")

    def collect_outputs(self, campaign_name: str, year: int, session: str) -> dict[str, Path]:
        raise NotImplementedError("WindowsBPEBackend is not yet implemented")
