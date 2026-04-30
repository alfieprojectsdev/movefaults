"""Unit tests for IGS product downloader (IGS20 naming + mirror fallback)."""

import gzip
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from pogf_geodetic_suite.igs_downloader import (
    ProductDownloader,
    _build_long_filename,
    _build_legacy_filename,
    _day_of_year,
    _gps_week,
)


# ---------------------------------------------------------------------------
# Filename construction
# ---------------------------------------------------------------------------

class TestBuildLongFilename:
    def test_cod_orb_known_date(self):
        # 2024-04-08 = DOY 099 in leap year (31+29+31+8 = 99)
        date = datetime(2024, 4, 8)
        assert _build_long_filename("COD", date, "ORB") == "COD0OPSFIN_20240990000_01D_05M_ORB.SP3.gz"

    def test_igs_orb_uses_15m_sampling(self):
        date = datetime(2024, 4, 9)
        fname = _build_long_filename("IGS", date, "ORB")
        assert "_15M_" in fname
        assert fname.endswith(".SP3.gz")

    def test_cod_clk_uses_30s_sampling(self):
        date = datetime(2024, 4, 9)
        fname = _build_long_filename("COD", date, "CLK")
        assert "_30S_" in fname
        assert fname.endswith(".CLK.gz")

    def test_igs_clk_uses_5m_sampling(self):
        date = datetime(2024, 4, 9)
        fname = _build_long_filename("IGS", date, "CLK")
        assert "_05M_" in fname

    def test_doy_zero_padded_3_digits(self):
        # Jan 1 → DOY 001
        date = datetime(2024, 1, 1)
        fname = _build_long_filename("COD", date, "ORB")
        assert "20240010000" in fname

    def test_leap_year_day_366(self):
        # Dec 31 of a leap year → DOY 366
        date = datetime(2024, 12, 31)
        fname = _build_long_filename("COD", date, "ORB")
        assert "20243660000" in fname

    def test_dec_31_non_leap_year(self):
        # Dec 31 of a non-leap year → DOY 365
        date = datetime(2023, 12, 31)
        fname = _build_long_filename("COD", date, "ORB")
        assert "20233650000" in fname


class TestDoyCalculation:
    def test_jan_1(self):
        assert _day_of_year(datetime(2024, 1, 1)) == 1

    def test_dec_31_leap(self):
        assert _day_of_year(datetime(2024, 12, 31)) == 366

    def test_dec_31_non_leap(self):
        assert _day_of_year(datetime(2023, 12, 31)) == 365

    def test_apr_9(self):
        assert _day_of_year(datetime(2024, 4, 9)) == 100


class TestBuildLegacyFilename:
    def test_cod_orb_format(self):
        assert _build_legacy_filename("COD", 2237, 3, "ORB") == "cod22373.sp3.Z"

    def test_igs_clk_format(self):
        assert _build_legacy_filename("IGS", 2237, 0, "CLK") == "igs22370.clk.Z"


# ---------------------------------------------------------------------------
# Mirror fallback
# ---------------------------------------------------------------------------

class TestMirrorFallback:
    def _make_response(self, status_code: int, content: bytes = b"") -> MagicMock:
        r = MagicMock()
        r.status_code = status_code
        r.content = content
        return r

    def test_first_mirror_success(self, tmp_path):
        payload = gzip.compress(b"FAKE SP3 DATA")
        downloader = ProductDownloader(
            base_dir=str(tmp_path),
            mirrors=["https://mirror1.example/", "https://mirror2.example/"],
        )
        with patch.object(downloader.session, "get", return_value=self._make_response(200, payload)) as mock_get:
            result = downloader.download_product(datetime(2024, 4, 9), ac="COD", content="ORB")

        assert result is not None
        assert os.path.exists(result)
        mock_get.assert_called_once()  # second mirror never tried

    def test_404_on_first_tries_second(self, tmp_path):
        payload = gzip.compress(b"FAKE SP3 DATA")
        responses = [
            self._make_response(404),
            self._make_response(200, payload),
        ]
        downloader = ProductDownloader(
            base_dir=str(tmp_path),
            mirrors=["https://mirror1.example/", "https://mirror2.example/"],
        )
        with patch.object(downloader.session, "get", side_effect=responses) as mock_get:
            result = downloader.download_product(datetime(2024, 4, 9), ac="COD", content="ORB")

        assert result is not None
        assert mock_get.call_count == 2

    def test_all_mirrors_fail_returns_none(self, tmp_path):
        downloader = ProductDownloader(
            base_dir=str(tmp_path),
            mirrors=["https://mirror1.example/", "https://mirror2.example/"],
        )
        with patch.object(downloader.session, "get", return_value=self._make_response(404)):
            result = downloader.download_product(datetime(2024, 4, 9), ac="COD", content="ORB")

        assert result is None

    def test_network_exception_falls_through_to_next_mirror(self, tmp_path):
        payload = gzip.compress(b"FAKE SP3 DATA")
        responses = [OSError("connection refused"), self._make_response(200, payload)]
        downloader = ProductDownloader(
            base_dir=str(tmp_path),
            mirrors=["https://mirror1.example/", "https://mirror2.example/"],
        )
        with patch.object(downloader.session, "get", side_effect=responses):
            result = downloader.download_product(datetime(2024, 4, 9), ac="COD", content="ORB")

        assert result is not None


# ---------------------------------------------------------------------------
# IGS20 transition: long vs legacy filename selection
# ---------------------------------------------------------------------------

class TestIGS20Transition:
    def test_post_transition_date_uses_long_filename(self, tmp_path):
        # GPS week 2309 >> 2238
        payload = gzip.compress(b"DATA")
        downloader = ProductDownloader(base_dir=str(tmp_path), mirrors=["https://m1/"])
        captured_urls: list[str] = []

        def _fake_get(url, **kwargs):
            captured_urls.append(url)
            r = MagicMock()
            r.status_code = 200
            r.content = payload
            return r

        with patch.object(downloader.session, "get", side_effect=_fake_get):
            downloader.download_product(datetime(2024, 4, 9), ac="COD", content="ORB")

        assert "COD0OPSFIN" in captured_urls[0]
        assert ".gz" in captured_urls[0]

    def test_pre_transition_date_uses_legacy_filename(self, tmp_path):
        # Use a date in GPS week 2237 (before transition)
        # GPS week 2237 starts 2022-11-20
        pre_transition_date = datetime(2022, 11, 20)
        downloader = ProductDownloader(base_dir=str(tmp_path), mirrors=["https://m1/"])
        captured_urls: list[str] = []

        def _fake_get(url, **kwargs):
            captured_urls.append(url)
            r = MagicMock()
            r.status_code = 404
            return r

        with patch.object(downloader.session, "get", side_effect=_fake_get):
            downloader.download_product(pre_transition_date, ac="COD", content="ORB")

        assert ".sp3.Z" in captured_urls[0]
        assert "COD0OPSFIN" not in captured_urls[0]


# ---------------------------------------------------------------------------
# Decompression + local file storage
# ---------------------------------------------------------------------------

class TestDecompression:
    def test_gz_content_is_decompressed_on_disk(self, tmp_path):
        inner = b"SP3 ORBIT DATA\n"
        payload = gzip.compress(inner)
        downloader = ProductDownloader(base_dir=str(tmp_path), mirrors=["https://m1/"])

        r = MagicMock()
        r.status_code = 200
        r.content = payload

        with patch.object(downloader.session, "get", return_value=r):
            local = downloader.download_product(datetime(2024, 4, 9), ac="COD", content="ORB")

        assert local is not None
        assert not local.endswith(".gz")
        assert open(local, "rb").read() == inner

    def test_skip_download_if_file_exists(self, tmp_path):
        downloader = ProductDownloader(base_dir=str(tmp_path), mirrors=["https://m1/"])

        # Pre-create the target file
        ddd = "100"
        target_dir = tmp_path / "2024" / ddd
        target_dir.mkdir(parents=True)
        existing = target_dir / "COD0OPSFIN_20241000000_01D_05M_ORB.SP3"
        existing.write_bytes(b"cached")

        with patch.object(downloader.session, "get") as mock_get:
            result = downloader.download_product(datetime(2024, 4, 9), ac="COD", content="ORB")

        mock_get.assert_not_called()
        assert result == str(existing)
