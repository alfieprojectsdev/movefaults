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


# ---------------------------------------------------------------------------
# Troposphere settings (GEO-003)
#
# `MAPPNG` / `NUMPAR` / `NUMGRD` live as literals in six GPSEST panels and have
# already drifted apart. Declaring them here does three things: it puts the
# current values somewhere a person can read without opening six files, it
# gives an F5-style mapping-function comparison one place to change, and --
# via the drift test in test_pcf_context.py -- it makes any future divergence
# fail loudly instead of being found by hand a second time.
#
# WHY PER PANEL, AND WHY NOTHING IS TEMPLATED YET
#
# GEO-003 proposed a single templated default on the grounds that it would be
# inert. Measuring the panels shows it would not: they hold THREE different
# mapping functions and TWO different estimation intervals. One default would
# silently change the science in five of six panels.
#
# The divergence is GEO-002's subject and the decision there is PHIVOLCS', not
# an engineering one. So this records reality per panel and changes no
# behaviour. Substituting `$(V_MAPPNG)` into the panels is a follow-up that
# should happen *after* GEO-002 decides what the values ought to be.
#
# One caution carried from GEO-002, worth repeating where someone will see it:
# do NOT shorten the troposphere interval. R2S_FIN already estimates zenith
# delay hourly -- shorter than the 3-hourly GSI used on PHIVOLCS' own Mindanao
# data (Tobita et al. 2015).
#
# Measured 2026-08-21 from config/bernese/gpsuser52-luzon/OPT/*/GPSEST.INP.


@dataclass(frozen=True)
class TroposphereSettings:
    """One GPSEST panel's troposphere estimation block."""

    mappng: str
    """Mapping function. COSZ is correct for the Melbourne-Wubbena panel;
    the WET_GMF / WET_NIELL split across the others is GEO-002's subject."""

    numpar: str
    """Zenith-delay estimation interval, "HH MM SS"."""

    numgrd: str
    """Gradient estimation interval. R2S_AMB's "1" is a count, not a time."""


LUZON_TROPOSPHERE: dict[str, TroposphereSettings] = {
    "R2S_AMB": TroposphereSettings("COSZ", "02 00 00", "1"),
    "R2S_EDT": TroposphereSettings("WET_GMF", "02 00 00", "24 00 00"),
    "R2S_FIN": TroposphereSettings("WET_GMF", "01 00 00", "24 00 00"),
    "R2S_L12": TroposphereSettings("WET_NIELL", "02 00 00", "24 00 00"),
    "R2S_L53": TroposphereSettings("WET_NIELL", "02 00 00", "24 00 00"),
    "R2S_QIF": TroposphereSettings("WET_NIELL", "02 00 00", "24 00 00"),
}
