import pytest
from pathlib import Path
from datetime import datetime, date
from src.sources.file import FileSource

@pytest.fixture
def sample_nmea_file(tmp_path):
    p = tmp_path / "test.nmea"
    content = """$GNLDM,113805.50,030215,113805.50,030215,0.0101,0.0204,0.0459,0.0021,0.0020,0.0041,0.00021,0.00023,0.00041,0.05,19,0,1,1*4C
$GNLDM,113806.50,030215,113805.50,030215,0.0102,0.0205,0.0460,0.0021,0.0020,0.0041,0.00021,0.00023,0.00041,0.05,19,0,1,1*4F
"""
    p.write_text(content)
    return p

@pytest.mark.asyncio
async def test_file_source_iteration(sample_nmea_file):
    source = FileSource(sample_nmea_file, mode="import")
    lines = []
    async for line in source:
        lines.append(line)
    
    assert len(lines) == 2
    assert "113805.50" in lines[0]
    assert "113806.50" in lines[1]

@pytest.mark.asyncio
async def test_file_source_replay_delay(sample_nmea_file):
    # This test verifies logically that delay would be called, 
    # but we don't want to actually sleep for 1 second in unit tests if we can avoid it.
    # We can rely on the logic being simple or mock asyncio.sleep.
    # For now, let's just run it; 1 second isn't too bad for a robust test.
    
    source = FileSource(sample_nmea_file, mode="replay")
    
    start = datetime.now()
    lines = []
    async for line in source:
        lines.append(line)
    end = datetime.now()
    
    # Delta between lines is 1 second (113805.50 to 113806.50)
    # So execution should take at least ~1 second
    duration = (end - start).total_seconds()
    assert duration >= 1.0

def test_extract_datetime():
    source = FileSource("dummy", base_date=date(2015, 2, 3))
    line = "$GNLDM,113805.50,..."
    dt = source._extract_datetime(line)
    assert dt == datetime(2015, 2, 3, 11, 38, 5)

def test_extract_datetime_rollover():
    source = FileSource("dummy", base_date=date(2015, 2, 3))
    
    # First time: 23:59:59
    source.last_timestamp = datetime(2015, 2, 3, 23, 59, 59)
    
    # Next time: 00:00:01 (jump back in time -> new day)
    line = "$GNLDM,000001.00,..."
    dt = source._extract_datetime(line)
    
    assert dt.date() == date(2015, 2, 4)
    assert dt.time().second == 1
