"""Data models for Bernese campaign configuration."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class StationRecord:
    """ECEF position + velocity for one CORS station."""
    name: str            # 4-char code, e.g. "BOST"
    x: float             # ECEF X (m)
    y: float             # ECEF Y (m)
    z: float             # ECEF Z (m)
    vx: float = 0.0      # velocity X (m/yr)
    vy: float = 0.0      # velocity Y (m/yr)
    vz: float = 0.0      # velocity Z (m/yr)
    receiver: str = "LEICA GR50"
    antenna: str = "LEIAR20"
    antenna_serial: str = "NONE"
    dome: str = "00000S000"   # DOMES placeholder when not assigned
    start: datetime = field(default_factory=lambda: datetime(1980, 1, 1))
    end: datetime = field(default_factory=lambda: datetime(2099, 12, 31))


@dataclass
class CampaignConfig:
    """Everything needed to populate a Bernese campaign directory."""
    campaign_name: str
    year: int
    session: str
    stations: list[StationRecord]
    ref_frame: str = "IGS14"
    epoch: str = "2015-01-01 00:00:00"
    # When set, this ATX file is copied/symlinked to <campaign>/ATM/
    atx_source: Path | None = None
    # Whether to fetch BLQ from Chalmers (disable in offline/test mode)
    download_blq: bool = True
    blq_model: str = "FES2014b"
    # Whether this is a continuous GPS (two-pass BPE) campaign
    continuous: bool = False
