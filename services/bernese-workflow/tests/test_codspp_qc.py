"""Tests for codspp_qc — fixtures are verbatim CODSPP SPP_*.OUT excerpts (RH-005)."""
from __future__ import annotations

import pytest
from bernese_workflow.codspp_qc import (
    CodsppStation,
    classify_codspp,
    parse_codspp_output,
    parse_codxtr_summary,
)

# Verbatim per-cluster CODSPP output (CUSV, session 0840) — good station.
_REAL_CLUSTER = """\
 USED OBSERVATIONS   :     43330
 BAD OBSERVATIONS    :         1.02 %
 RMS OF UNIT WEIGHT  :         1.03 M
 NUMBER OF ITERATIONS:         2


 STATION COORDINATES:
 --------------------

 LOCAL GEODETIC DATUM:  IGS20

                                    A PRIORI         NEW            NEW- A PRIORI   RMS ERROR
  CUSV 21904S001    X             -1132915.14     -1132915.19           -0.05         0.01
  (MARKER)          Y              6092528.50      6092528.26           -0.24         0.02
                    Z              1504633.10      1504633.01           -0.09         0.01

                    HEIGHT              74.23           73.99           -0.24         0.02
"""

# Verbatim CODXTR combined summary tail.
_REAL_SUMMARY = """\
  72 FILES, MAX. RMS:    2.58 M    FOR STATION: PSRF 22032M001
            MAX. BAD:    4.54 %    FOR STATION: PAPI 22055M001
            MAX. OFF:   -0.00 MSEC FOR STATION: PCB2 22010M002
"""


# ---------------------------------------------------------------------------
# parse_codspp_output
# ---------------------------------------------------------------------------

def test_parse_real_cluster():
    st = parse_codspp_output(_REAL_CLUSTER)
    assert st.station == "CUSV"
    assert st.rms_unit_weight_m == pytest.approx(1.03)
    assert st.bad_obs_pct == pytest.approx(1.02)
    assert st.used_obs == 43330
    assert st.dx == pytest.approx(-0.05)
    assert st.dy == pytest.approx(-0.24)
    assert st.dz == pytest.approx(-0.09)


def test_coord_shift_magnitude():
    st = parse_codspp_output(_REAL_CLUSTER)
    # sqrt(0.05^2 + 0.24^2 + 0.09^2) ≈ 0.261
    assert st.coord_shift_m == pytest.approx(0.261, abs=1e-3)


def test_parse_truncated_is_all_none_no_crash():
    st = parse_codspp_output("garbage\nno coordinates here\n")
    assert st.station is None
    assert st.rms_unit_weight_m is None
    assert st.coord_shift_m is None


# ---------------------------------------------------------------------------
# classify_codspp
# ---------------------------------------------------------------------------

def test_classify_real_station_ok():
    assert classify_codspp(parse_codspp_output(_REAL_CLUSTER)) == "ok"


def test_classify_bad_apriori():
    # high RMS + large shift → seed coords wrong, auto-fixable.
    st = CodsppStation("BADA", rms_unit_weight_m=5.0, bad_obs_pct=2.0,
                       used_obs=1000, dx=3.0, dy=0.0, dz=0.0)
    assert classify_codspp(st) == "bad_apriori"


def test_classify_bad_obs():
    # high RMS + small shift → data problem, needs a human.
    st = CodsppStation("BOBS", rms_unit_weight_m=5.0, bad_obs_pct=9.0,
                       used_obs=1000, dx=0.1, dy=0.1, dz=0.1)
    assert classify_codspp(st) == "bad_obs"


def test_classify_unknown_when_rms_missing():
    st = CodsppStation("NONE", None, None, None, None, None, None)
    assert classify_codspp(st) == "unknown"


def test_classify_threshold_tunable():
    st = parse_codspp_output(_REAL_CLUSTER)  # rms 1.03, shift 0.26
    # Tighten RMS threshold below the real value → now flagged; small shift → bad_obs.
    assert classify_codspp(st, rms_threshold_m=0.5) == "bad_obs"


# ---------------------------------------------------------------------------
# parse_codxtr_summary
# ---------------------------------------------------------------------------

def test_parse_codxtr_summary():
    s = parse_codxtr_summary(_REAL_SUMMARY)
    assert s.max_rms_m == pytest.approx(2.58)
    assert s.max_rms_station == "PSRF"
    assert s.max_bad_pct == pytest.approx(4.54)
    assert s.max_bad_station == "PAPI"
