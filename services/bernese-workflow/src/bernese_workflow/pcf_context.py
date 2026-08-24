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


# WHICH TREE THIS DESCRIBES -- read before trusting it (corrected 2026-08-24).
#
# These values are measured from `config/bernese/gpsuser52-luzon/OPT`, which is
# PHIVOLCS' **5.2** panel set. That is NOT what the R740 executes. The live 5.4
# tree at `$U/OPT` (`/home/gps3/GPSUSER/OPT`) differs on the two panels that
# matter most:
#
#     panel      here (5.2 repo)   LIVE 5.4 tree
#     R2S_EDT    WET_GMF           WET_GMF3
#     R2S_FIN    WET_GMF           WET_GMF3
#
# `WET_GMF` and `WET_GMF3` are both valid 5.4 cards and they are different
# functions -- GMF is the 2006 Global Mapping Function, GMF3 the GPT3/VMF3-era
# gridded successor. Every LUZON solution produced on the R740, including the
# 30-day 2026-08-06 run, used GMF3. GEO-002's table and this one both say GMF.
#
# So the drift test that guards this table proves the 5.2 config has not
# changed. It says nothing about the configuration that actually produces
# numbers, and it never fired despite a live/declared mismatch existing the
# whole time. A guard pointed at the wrong tree reads exactly like a guard.
#
# Not "fixed" here by editing the values: which tree is authoritative is a
# project decision, and silently repointing this table would swap one
# unexamined claim for another. What is fixed is the claim -- the table now
# says what it describes. See `docs/project_documentation/
# bernese_workflow_geonet_actions.md` §1.2 and the session log.
LUZON_TROPOSPHERE: dict[str, TroposphereSettings] = {
    "R2S_AMB": TroposphereSettings("COSZ", "02 00 00", "1"),
    "R2S_EDT": TroposphereSettings("WET_GMF", "02 00 00", "24 00 00"),
    "R2S_FIN": TroposphereSettings("WET_GMF", "01 00 00", "24 00 00"),
    "R2S_L12": TroposphereSettings("WET_NIELL", "02 00 00", "24 00 00"),
    "R2S_L53": TroposphereSettings("WET_NIELL", "02 00 00", "24 00 00"),
    "R2S_QIF": TroposphereSettings("WET_NIELL", "02 00 00", "24 00 00"),
}
