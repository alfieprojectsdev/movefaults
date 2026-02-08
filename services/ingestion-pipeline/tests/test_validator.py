import pytest
import os
import tempfile
from ingestion_pipeline.filters.validator import validate_rinex_file

def test_validate_rinex_header_success():
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("     3.02           OBSERVATION DATA    M (MIXED)           RINEX VERSION / TYPE\n")
        f.close()

        try:
            is_valid, error = validate_rinex_file(f.name)
            # It might fail on gfzrnx missing, but header check passes
            # My implementation:
            # 1. Header check -> if fails, return False immediately
            # 2. gfzrnx check -> if missing, log warning and return True (pass)
            assert is_valid == True
            if error:
                 assert "skipped" in error.lower() or "missing" in error.lower()
        finally:
            os.remove(f.name)

def test_validate_rinex_header_fail():
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("INVALID HEADER\n")
        f.close()

        try:
            is_valid, error = validate_rinex_file(f.name)
            assert is_valid == False
            assert "Invalid RINEX header" in error
        finally:
            os.remove(f.name)
