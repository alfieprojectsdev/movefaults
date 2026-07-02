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
    # Clustering (RH-006 / gap #13). v_clu = files per parallel processing cluster.
    # v_clufin = final-solution clustering mode in GPSCLU ("A" auto / "N" skip). "A"
    # made ONE giant single-core solve on the full network; the value that splits the
    # final solve across cores is empirical and needs the R740 to tune (BRN-001).
    v_clu: str = "10"
    v_clufin: str = "A"

    def to_dict(self) -> dict[str, str]:
        return {k: str(v) for k, v in asdict(self).items()}
