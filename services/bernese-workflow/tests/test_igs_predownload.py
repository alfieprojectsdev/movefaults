"""Tests for RH-007 — IGS product pre-download wiring + pre-flight verify + template."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from bernese_workflow.campaign_builder import verify_igs_products
from pogf_geodetic_suite.igs_downloader import _build_long_filename


def _stage_product(orb: Path, year: int, doy: int, ac: str, content: str) -> Path:
    """Create the decompressed product file exactly where ProductDownloader would."""
    date = datetime(year, 1, 1) + timedelta(days=doy - 1)
    name = _build_long_filename(ac, date, content).removesuffix(".gz")
    dest = orb / str(year) / f"{doy:03d}" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("stub")
    return dest


# ---------------------------------------------------------------------------
# verify_igs_products
# ---------------------------------------------------------------------------

def test_verify_missing_when_empty(tmp_path):
    missing = verify_igs_products(tmp_path / "ORB", 2026, 87)
    assert len(missing) == 2  # ORB + CLK both absent


def test_verify_present_when_staged(tmp_path):
    orb = tmp_path / "ORB"
    _stage_product(orb, 2026, 87, "COD", "ORB")
    _stage_product(orb, 2026, 87, "COD", "CLK")
    assert verify_igs_products(orb, 2026, 87) == []


def test_verify_reports_the_one_missing(tmp_path):
    orb = tmp_path / "ORB"
    _stage_product(orb, 2026, 87, "COD", "ORB")  # only ORB present
    missing = verify_igs_products(orb, 2026, 87)
    assert len(missing) == 1
    assert "CLK" in missing[0]


def test_verify_legacy_era_raises(tmp_path):
    # 2020 is pre-IGS20 (GPS week < 2238) → not supported by the long-name check.
    with pytest.raises(NotImplementedError, match="IGS20"):
        verify_igs_products(tmp_path / "ORB", 2020, 1)


# ---------------------------------------------------------------------------
# Template: FTP_DWLD retired
# ---------------------------------------------------------------------------

def test_template_has_no_ftp_dwld():
    tpl = (
        Path(__file__).resolve().parents[1] / "templates" / "basic_processing.pcf.j2"
    ).read_text()
    assert "FTP_DWLD" not in tpl
    # 001 R2S_COP must no longer WAIT on the removed 000.
    line = next(ln for ln in tpl.splitlines() if ln.startswith("001 R2S_COP"))
    assert line.split()[-1] != "000"


# ---------------------------------------------------------------------------
# prepare_campaign wiring (opt-in; prefetch mocked — no network)
# ---------------------------------------------------------------------------

def test_prepare_prefetch_disabled_by_default(tmp_path, monkeypatch):
    import bernese_workflow.campaign_builder as cb
    from bernese_workflow.backends import LinuxBPEBackend

    called = {"n": 0}
    monkeypatch.setattr(cb, "prefetch_igs_products",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))

    LinuxBPEBackend(
        bernese_root=tmp_path / "BERN54",
        user_dir=tmp_path / "GPSUSER",
        campaign_dir=tmp_path / "GPSDATA",
    ).prepare_campaign("PAGENET", 2026, "0870")  # prefetch_products defaults False
    assert called["n"] == 0


def test_prepare_prefetch_calls_and_verifies(tmp_path, monkeypatch):
    import bernese_workflow.campaign_builder as cb
    from bernese_workflow.backends import LinuxBPEBackend

    calls = {"prefetch": 0}
    monkeypatch.setattr(cb, "prefetch_igs_products",
                        lambda *a, **k: calls.__setitem__("prefetch", calls["prefetch"] + 1))
    monkeypatch.setattr(cb, "verify_igs_products", lambda *a, **k: [])  # all present

    LinuxBPEBackend(
        bernese_root=tmp_path / "BERN54",
        user_dir=tmp_path / "GPSUSER",
        campaign_dir=tmp_path / "GPSDATA",
    ).prepare_campaign("PAGENET", 2026, "0870", prefetch_products=True)
    assert calls["prefetch"] == 1


def test_prepare_prefetch_raises_on_missing(tmp_path, monkeypatch):
    import bernese_workflow.campaign_builder as cb
    from bernese_workflow.backends import LinuxBPEBackend

    monkeypatch.setattr(cb, "prefetch_igs_products", lambda *a, **k: None)
    monkeypatch.setattr(cb, "verify_igs_products", lambda *a, **k: ["2026/087/COD..CLK"])

    with pytest.raises(RuntimeError, match="IGS products incomplete"):
        LinuxBPEBackend(
            bernese_root=tmp_path / "BERN54",
            user_dir=tmp_path / "GPSUSER",
            campaign_dir=tmp_path / "GPSDATA",
        ).prepare_campaign("PAGENET", 2026, "0870", prefetch_products=True)
