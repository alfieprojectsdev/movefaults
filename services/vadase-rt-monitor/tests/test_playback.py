"""Unit tests for playback strategies (realtime pacing + day rollover)."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from src.strategies.playback import RealTimeStrategy


def _lvm(hhmmss: str) -> str:
    return f"$GNLVM,{hhmmss}.00,020126,0.001,0.002,0.003*4F"


@pytest.mark.asyncio
async def test_forward_step_sleeps_and_keeps_date():
    """Two consecutive 1 Hz samples must sleep ~1 s and NOT advance the date.

    Regression: (last - dt).seconds on a negative timedelta normalizes to
    days=-1, seconds=86399 — which falsely triggered the day-rollover branch
    on every normal forward step, so RealTimeStrategy never slept at all.
    """
    strategy = RealTimeStrategy(base_date=date(2026, 1, 2))
    start_date = strategy.current_date

    with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await strategy.wait(_lvm("140000"))
        await strategy.wait(_lvm("140001"))

    mock_sleep.assert_awaited_once()
    assert mock_sleep.await_args.args[0] == pytest.approx(1.0)
    assert strategy.current_date == start_date, "date must not advance on a forward step"


@pytest.mark.asyncio
async def test_midnight_rollover_advances_date():
    """A time jump backwards past midnight advances current_date by one day."""
    strategy = RealTimeStrategy(base_date=date(2026, 1, 2))

    with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await strategy.wait(_lvm("235959"))
        await strategy.wait(_lvm("000001"))  # 2 s later, next day

    assert strategy.current_date == date(2026, 1, 3)
    mock_sleep.assert_awaited_once()
    assert mock_sleep.await_args.args[0] == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_speed_multiplier_divides_sleep():
    """--speed 8 must sleep delta/8."""
    strategy = RealTimeStrategy(base_date=date(2026, 1, 2), speed=8.0)

    with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await strategy.wait(_lvm("140000"))
        await strategy.wait(_lvm("140004"))  # 4 s apart

    mock_sleep.assert_awaited_once()
    assert mock_sleep.await_args.args[0] == pytest.approx(0.5)
