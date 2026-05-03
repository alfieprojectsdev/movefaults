from __future__ import annotations

from dataclasses import dataclass


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
        return {
            "v_crdinf": self.v_crdinf,
            "v_rnxdir": self.v_rnxdir,
            "v_b": self.v_b,
            "v_refinf": self.v_refinf,
            "v_sampl": self.v_sampl,
            "v_satsys": self.v_satsys,
            "v_hoifil": self.v_hoifil,
        }
