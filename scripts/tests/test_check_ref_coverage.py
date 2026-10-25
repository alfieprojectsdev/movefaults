"""
scripts/check_ref_coverage.py reads Bernese reference files the way Bernese
does. Each test pins one of the three ways an entry can be present in a file
and still be reported NOT FOUND (docs/SETTLED.md §2), plus the plain absences.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "check_ref_coverage", Path(__file__).resolve().parents[1] / "check_ref_coverage.py"
)
cov = importlib.util.module_from_spec(_spec)
sys.modules["check_ref_coverage"] = cov
_spec.loader.exec_module(cov)

CRD = (
    "                                                                 11-AUG-26 22:56\r\n"
    "--------------------------------------------------------------------------------\r\n"
    "LOCAL GEODETIC DATUM: IGS14             EPOCH: 2026-02-12 00:00:00\r\n"
    "\r\n"
    "NUM  STATION NAME           X (M)          Y (M)          Z (M)     FLAG\r\n"
    "\r\n"
    "  1  AGUS AGUS        -3442268.43853  5197451.98331  1343779.24890\r\n"
    "316  PTAG 22006M005   -3184318.48238  5291065.65065  1590418.29284    A\r\n"
)

BLQ_HEAD = "$$ Ocean loading displacement\r\n$$\r\n$$ END HEADER\r\n$$\r\n"
BLOCK = (
    "$$ FES2004_PP ID: 2026-09-30 10:07:52\r\n"
    "$$\r\n"
    "$$ {c},                      RADI TANG  lon/lat:  125.1904    1.4389   74.914\r\n"
    + "  .01671 .00928 .00304 .00231 .01029 .00813 .00341 .00194 .00112 .00065 .00057\r\n"
    * 6
)


def blq(*parts: str) -> str:
    return BLQ_HEAD + "".join(parts)


def block(code: str, indent: str = "  ") -> str:
    return f"{indent}{code}\r\n" + BLOCK.format(c=code)


END = "$$ END TABLE\r\n"


def test_crd_names_keep_the_full_sixteen_character_name():
    assert cov.crd_names(CRD) == {"AGUS": ["AGUS AGUS"], "PTAG": ["PTAG 22006M005"]}


def test_blq_block_before_end_table_is_found():
    assert cov.blq_status(blq(block("AGUS"), END), "AGUS") == "ok"


def test_blq_block_after_end_table_is_reported_as_unread():
    assert cov.blq_status(blq(END, block("AGUS")), "AGUS") == "after END TABLE"


def test_blq_block_indented_one_column_left_is_reported():
    assert cov.blq_status(blq(block("AGUS", indent=" "), END), "AGUS") == "indented 1 column"


def test_blq_station_absent():
    assert cov.blq_status(blq(block("AGUS"), END), "PTAG") == "absent"


def test_blq_comment_mentioning_the_code_does_not_count():
    # the guard that once passed on PTTN matched a comment line
    assert cov.blq_status(blq("$$ PTAG, mentioned only here\r\n", END), "PTAG") == "absent"


def test_atl_header_must_equal_the_crd_name():
    atl = "$$ header\r\nPTAG 22006M005\r\n     -0.2  0.3 -0.7 -0.9\r\n \r\n"
    assert cov.atl_status(atl, "PTAG 22006M005") == "ok"


def test_atl_bare_code_header_is_a_name_mismatch():
    atl = "$$ header\r\nPTAG \r\n     -0.2  0.3 -0.7 -0.9\r\n \r\n"
    assert cov.atl_status(atl, "PTAG 22006M005") == "header 'PTAG' != 'PTAG 22006M005'"


def test_atl_bare_header_is_fine_when_the_crd_name_is_bare():
    # PGN.CRD writes PBOG bare, so PGN.ATL's bare header is correct
    atl = "PBOG\r\n     -0.2  0.3 -0.7 -0.9\r\n \r\n"
    assert cov.atl_status(atl, "PBOG") == "ok"


def test_atl_station_absent():
    assert cov.atl_status("AGUS AGUS\r\n 0 0 0 0\r\n \r\n", "PTAG 22006M005") == "absent"


def test_name_listed_matches_full_name_at_line_start_only():
    sta = "PTAG 22006M005        001  2008 09 23 00 00 00   PTAG*   IGS.SNX\r\n"
    assert cov.name_listed(sta, "PTAG 22006M005")
    assert not cov.name_listed(sta, "AGUS AGUS")
    assert not cov.name_listed("  remark about PTAG 22006M005\r\n", "PTAG 22006M005")


def test_check_reports_only_problems_and_names_the_file():
    files = {
        "CRD": CRD,
        "STA": "AGUS AGUS  001\r\nPTAG 22006M005  001\r\n",
        "ABB": "AGUS AGUS   AGUS A1\r\nPTAG 22006M005  PTAG P2\r\n",
        "BLQ": blq(block("AGUS"), END, block("PTAG")),
        "ATL": "AGUS AGUS\r\n 0 0 0 0\r\nPTAG \r\n 0 0 0 0\r\n \r\n",
    }
    problems = cov.check(["AGUS", "PTAG", "XXXX"], files)
    assert ("PTAG", "BLQ", "after END TABLE") in problems
    assert ("PTAG", "ATL", "header 'PTAG' != 'PTAG 22006M005'") in problems
    assert ("XXXX", "CRD", "absent") in problems
    assert not any(p[0] == "AGUS" for p in problems)


PCF = (
    "V_CRDINF = PHNAT;          DESCRIPTION=Merged CRD/VEL filename\n"
    "V_STAINF = PHNAT;          DESCRIPTION=_Station information file\n"
    "V_CRXINF = ;               DESCRIPTION=_Accepted station inform\n"
    "V_BLQINF = PHNAT;          DESCRIPTION=_BLQ file name, CMC corrections\n"
    "V_ATLINF = ;               DESCRIPTION=_ATL file name, CMC corrections\n"
)


def test_pcf_resolves_each_file_the_way_r2s_cop_does():
    # R2S_COP: CRD and ABB from V_CRDINF, STA from V_STAINF, BLQ/ATL from their own
    assert cov.pcf_sets(PCF) == {
        "CRD": "PHNAT",
        "ABB": "PHNAT",
        "STA": "PHNAT",
        "BLQ": "PHNAT",
        "ATL": "",
    }


def test_pcf_missing_variable_is_an_error_not_a_blank():
    try:
        cov.pcf_sets("V_CRDINF = PHNAT;\n")
    except KeyError as e:
        assert "V_STAINF" in str(e)
    else:
        raise AssertionError("a PCF without V_STAINF must not resolve")


def test_a_file_the_pcf_leaves_blank_is_not_checked():
    # R2S_COP skips BLQ/ATL when the variable is empty; so must the check
    files = {
        "CRD": CRD,
        "STA": "AGUS AGUS  001\r\n",
        "ABB": "AGUS AGUS   AGUS A1\r\n",
        "BLQ": blq(block("AGUS"), END),
        "ATL": None,
    }
    assert cov.check(["AGUS"], files) == []


# --- review of #283 -------------------------------------------------------


def test_name_listed_bare_name_is_not_satisfied_by_a_longer_name():
    # PGN.CRD writes PTAG bare; an STA line for "PTAG 22006M005" is a different
    # 16-character key and must not count as listing "PTAG"
    sta = "PTAG 22006M005        001  2008 09 23 00 00 00   PTAG*   IGS.SNX\r\n"
    assert not cov.name_listed(sta, "PTAG")
    assert cov.name_listed("PTAG                  001\r\n", "PTAG")


def test_blq_header_for_a_longer_name_is_not_the_code():
    assert cov.blq_status(blq(block("AGUSX"), END), "AGUS") == "absent"


# LUZON.CRD carries BILI twice: the IGS fiducial and the PHIVOLCS site
CRD_DUP = (
    "NUM  STATION NAME           X (M)          Y (M)          Z (M)     FLAG\r\n"
    "\r\n"
    " 44  BILI BILI        -3538708.71944  5153833.93735  1259526.87920\r\n"
    " 43  BILI 12363M001   -2321893.42497   560096.77934  5894691.66481\r\n"
)


def test_duplicate_crd_code_resolves_through_the_sta_file():
    files = {
        "CRD": CRD_DUP,
        "STA": "BILI BILI             001\r\n",
        "ABB": "BILI BILI                BILI     BI\r\n",
        "BLQ": blq(block("BILI"), END),
        "ATL": "BILI BILI\r\n 0 0 0 0\r\n \r\n",
    }
    # order in the CRD must not decide which name is checked
    assert cov.check(["BILI"], files) == []


def test_duplicate_crd_code_that_sta_cannot_resolve_is_reported():
    files = {
        "CRD": CRD_DUP,
        "STA": "BILI BILI             001\r\nBILI 12363M001        001\r\n",
        "ABB": "BILI BILI                BILI     BI\r\n",
        "BLQ": blq(block("BILI"), END),
        "ATL": None,
    }
    problems = cov.check(["BILI"], files)
    assert [p[:2] for p in problems] == [("BILI", "CRD")]
    assert "ambiguous" in problems[0][2]


def _run_main(monkeypatch, tmp_path, argv):
    monkeypatch.setattr(sys, "argv", ["check_ref_coverage.py", *argv])
    return cov.main()


def test_pcf_with_empty_stainf_is_an_error_not_a_crash(monkeypatch, tmp_path, capsys):
    pcf_dir = tmp_path / "PCF"
    pcf_dir.mkdir()
    (pcf_dir / "X_DLY.PCF").write_text(
        "V_CRDINF = PHNAT;\nV_STAINF = ;\nV_BLQINF = ;\nV_ATLINF = ;\n"
    )
    ref = tmp_path / "REF54"
    ref.mkdir()
    for kind in ("CRD", "ABB"):
        (ref / f"PHNAT.{kind}").write_text(CRD)
    sites = tmp_path / "sites.txt"
    sites.write_text("AGUS\n")
    rc = _run_main(
        monkeypatch,
        tmp_path,
        [
            "--pcf",
            "X_DLY",
            "--pcf-dir",
            str(pcf_dir),
            "--ref-dir",
            str(ref),
            "--stations",
            str(sites),
        ],
    )
    assert rc == 2
    assert "V_STAINF" in capsys.readouterr().err


def test_missing_station_list_exits_2_not_1(monkeypatch, tmp_path):
    ref = tmp_path / "REF54"
    ref.mkdir()
    for kind in cov.KINDS:
        (ref / f"S.{kind}").write_text("")
    rc = _run_main(
        monkeypatch,
        tmp_path,
        ["--set", "S", "--ref-dir", str(ref), "--stations", str(tmp_path / "nope.txt")],
    )
    assert rc == 2
