
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta
from src.domain.processor import IngestionCore
from src.ports.outputs import OutputPort

class MockOutputPort(OutputPort):
    async def connect(self): pass
    async def close(self): pass
    async def write_velocity(self, station_id, data): pass
    async def write_displacement(self, station_id, data): pass
    async def write_event_detection(self, station_id, start_time, peak_v, peak_d, duration): pass

@pytest.mark.asyncio
async def test_processor_redundant_calculation():
    # Setup
    output_port = MockOutputPort()
    core = IngestionCore(
        station_id="TEST",
        output_port=output_port,
        decay_factor=0.9
    )

    # Initial state
    core.disp_up = 10.0
    core.last_velocity_time = datetime(2023, 1, 1, 12, 0, 0)

    # Input data
    sentence = "$GNLVM,120001.00,010123,120001.00,010123,0.1,0.2,0.3,0.01,0.02,0.03,0.001,0.002,0.003,0.5,10,0,1,1*6D"
    # We need to parse this sentence to get vU=0.3. The parse_lvm mock or actual parser is needed.
    # But IngestionCore calls parse_lvm internally. So we can just use handle_velocity directly?
    # Or better, just manually call handle_velocity logic or verify the outcome after calling handle_velocity

    # But wait, handle_velocity parses the sentence. I should just construct a valid sentence or mock parse_lvm.
    # Easier to just construct a valid sentence if possible.
    # The checksum *6D might be wrong.
    # Let's use a simpler approach: Instantiate Core, set internal state, and call a method that triggers the logic.
    # But the logic is inside handle_velocity which parses the string.

    # Alternatively, I can mock parse_lvm.
    with pytest.MonkeyPatch.context() as m:
        from src.domain import processor

        mock_data = {
            'timestamp': datetime(2023, 1, 1, 12, 0, 1), # 1 second later
            'vE': 0.1,
            'vN': 0.2,
            'vU': 0.5, # vertical velocity
            'vH_magnitude': 0.0 # doesn't matter
        }

        m.setattr(processor, "parse_lvm", lambda x: mock_data)
        m.setattr(processor, "compute_horizontal_magnitude", lambda x, y: 0.0)
        m.setattr(processor, "convert_m_to_mm", lambda x: 0.0)

        await core.handle_velocity("dummy_sentence")

        # Expected calculation:
        # delta_t = 1.0
        # disp_up = (disp_up_old * decay) + (vU * delta_t)
        # disp_up = (10.0 * 0.9) + (0.5 * 1.0) = 9.0 + 0.5 = 9.5

        # Current buggy calculation does it twice:
        # disp_up = 9.5
        # disp_up = (9.5 * 0.9) + (0.5 * 1.0) = 8.55 + 0.5 = 9.05

        assert core.disp_up == pytest.approx(9.5), f"Expected 9.5, got {core.disp_up}"
