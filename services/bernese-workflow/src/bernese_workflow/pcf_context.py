from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class PCFContext:
    """Typed context for rendering the PHIVOL_REL PCF Jinja2 template."""

    v_crdinf: str
    v_rnxdir: str
    v_b: str = "IGS"
    v_refinf: str = "IGS14"
    v_sampl: str = "180"
    v_satsys: str = "GPS"
    v_hoifil: str = "HOI$YSS+0"

    def to_dict(self) -> dict[str, str]:
        return {k: str(v) for k, v in asdict(self).items()}
