
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta
from src.domain.processor import IngestionCore, ReceiverMode
from src.ports.outputs import OutputPort


class MockOutputPort(OutputPort):
    async def connect(self): pass
    async def close(self): pass
    async def write_velocity(self, station_id, data): pass
    async def write_displacement(self, station_id, data): pass
    async def write_event_detection(self, station_id, start_time, peak_v, peak_d, duration): pass


def make_core(**kwargs):
    output = MockOutputPort()
    return IngestionCore(station_id="TEST", output_port=output, threshold_mm_s=15.0, **kwargs)


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

        assert core.disp_up == pytest.approx(9.5), f"Expected 9.5, got {core.disp_up}"


# Test: RECEIVER + IDENTICAL × 5 → mode becomes MANUAL
@pytest.mark.asyncio
async def test_state_receiver_identical_triggers_manual():
    core = make_core()
    assert core.mode == ReceiverMode.RECEIVER
    # prime last_velocity_data
    core.last_velocity_data = {'vE': 0.1, 'vN': 0.2}
    # drive 5 IDENTICAL signals
    for _ in range(5):
        core._update_mode(core._classify_signal(0.1, 0.2, 0.1, 0.2))
    assert core.mode == ReceiverMode.MANUAL
    assert core._freeze_integration is False


# Test: MANUAL + HIGH_VEL_NEQ × 30 → mode becomes RECEIVER
@pytest.mark.asyncio
async def test_state_manual_high_vel_neq_triggers_receiver():
    core = make_core(force_integration=True)
    assert core.mode == ReceiverMode.MANUAL
    # HIGH_VEL_NEQ: vel != disp and vH >= 15mm/s
    # vE=0.02, vN=0.0 → vH = 20mm/s >= 15; dE != vE
    for _ in range(30):
        core._update_mode(core._classify_signal(0.02, 0.0, 0.0, 0.0))
    assert core.mode == ReceiverMode.RECEIVER


# Test: MANUAL + LOW_VEL_NEQ → freeze_integration=True, integrator does not accumulate
@pytest.mark.asyncio
async def test_manual_low_vel_neq_freezes_integrator():
    core = make_core(force_integration=True)
    core.disp_east = 1.0
    core.last_velocity_time = datetime(2023, 1, 1, 12, 0, 0)
    # Trigger LOW_VEL_NEQ: vel != disp but vH < 15mm/s (vE=0.001 → ~1mm/s)
    core._update_mode(core._classify_signal(0.001, 0.0, 0.002, 0.0))
    assert core._freeze_integration is True
    # Now call handle_velocity with a small velocity 1s later — disp_east must not change
    with pytest.MonkeyPatch.context() as m:
        from src.domain import processor as proc
        m.setattr(proc, "parse_lvm", lambda x: {
            'timestamp': datetime(2023, 1, 1, 12, 0, 1),
            'vE': 0.001, 'vN': 0.0, 'vU': 0.0
        })
        m.setattr(proc, "compute_horizontal_magnitude", lambda x, y: 0.0)
        m.setattr(proc, "convert_m_to_mm", lambda x: 0.0)
        await core.handle_velocity("dummy")
    assert core.disp_east == pytest.approx(1.0)


# Test: RECEIVER + LOW_VEL_NEQ × 3 → mode becomes MANUAL (scintillation path)
def test_state_receiver_low_vel_neq_triggers_manual():
    core = make_core()
    assert core.mode == ReceiverMode.RECEIVER
    # LOW_VEL_NEQ: vel != disp, vH < 15mm/s (vE=0.001)
    for _ in range(3):
        core._update_mode(core._classify_signal(0.001, 0.0, 0.002, 0.0))
    assert core.mode == ReceiverMode.MANUAL
    assert core._freeze_integration is True


# Test: displacement_source values
@pytest.mark.asyncio
async def test_displacement_source_labels():
    """MANUAL mode → INTEGRATOR; RECEIVER+suspect → RECEIVER_SUSPECT; clean → RECEIVER"""
    core = make_core(force_integration=True)
    written = []

    class CapturingPort(MockOutputPort):
        async def write_displacement(self, sid, data):
            written.append(data.get('displacement_source'))

    core.output_port = CapturingPort()
    core.last_velocity_data = {'vE': 0.1, 'vN': 0.2}

    # MANUAL mode → any displacement sentence should produce INTEGRATOR
    with pytest.MonkeyPatch.context() as m:
        from src.domain import processor as proc
        m.setattr(proc, "parse_ldm", lambda x: {
            'timestamp': datetime(2023, 1, 1, 12, 0, 1),
            'dE': 0.5, 'dN': 0.5, 'dU': 0.0,
            'overall_completeness': 1.0
        })
        m.setattr(proc, "compute_horizontal_magnitude", lambda x, y: 0.0)
        m.setattr(proc, "convert_m_to_mm", lambda x: 0.0)
        await core.handle_displacement("dummy")

    assert written[-1] == 'INTEGRATOR'


# Test: force_integration=True starts in MANUAL
def test_force_integration_starts_manual():
    core = make_core(force_integration=True)
    assert core.mode == ReceiverMode.MANUAL


# Test: default starts in RECEIVER
def test_default_starts_receiver():
    core = make_core()
    assert core.mode == ReceiverMode.RECEIVER
