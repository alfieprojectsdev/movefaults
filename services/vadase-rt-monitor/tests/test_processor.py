import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timedelta, timezone
from src.domain.processor import IngestionCore
from src.ports.outputs import OutputPort

@pytest.mark.asyncio
async def test_duplicate_integration_fix():
    # Setup
    mock_output = AsyncMock(spec=OutputPort)
    core = IngestionCore(station_id="TEST", output_port=mock_output)

    # Mock parse_lvm to return valid data
    timestamp = datetime.now(timezone.utc)
    core.last_velocity_time = timestamp

    # Prepare data for integration
    with patch('src.domain.processor.parse_lvm') as mock_parse:
        mock_parse.return_value = {
            'timestamp': timestamp + timedelta(seconds=1),
            'vE': 1.0, 'vN': 0.0, 'vU': 1.0, # moving up
            'quality': 1, 'cq': 1,
            'vH_magnitude': 0.0
        }

        # Initial state
        core.disp_up = 0.0
        core.decay_factor = 1.0 # No decay for simpler math

        # Call handle_velocity
        await core.handle_velocity("$GNLVM,dummy")

        # Assert integration
        # delta_t = 1.0
        # disp_up = (0 * 1) + (1.0 * 1.0) = 1.0
        # If duplicated, it would be:
        # 1st: disp_up = 1.0
        # 2nd: disp_up = (1.0 * 1.0) + (1.0 * 1.0) = 2.0

        assert core.disp_up == 1.0

@pytest.mark.asyncio
async def test_reset_indicator():
    mock_output = AsyncMock(spec=OutputPort)
    core = IngestionCore(station_id="TEST", output_port=mock_output)

    # Set initial state
    core.disp_east = 10.0
    core.disp_north = 10.0
    core.disp_up = 10.0

    # Mock parse_ldm with reset_indicator=1
    with patch('src.domain.processor.parse_ldm') as mock_parse:
        mock_parse.return_value = {
            'timestamp': datetime.now(timezone.utc),
            'dE': 5.0, 'dN': 5.0, 'dU': 5.0,
            'reset_indicator': 1,
            'overall_completeness': 1.0,
            'cq': 1,
            'dH_magnitude': 0.0
        }

        await core.handle_displacement("$GNLDM,dummy")

        # Assert reset
        assert core.disp_east == 5.0
        assert core.disp_north == 5.0
        assert core.disp_up == 5.0
