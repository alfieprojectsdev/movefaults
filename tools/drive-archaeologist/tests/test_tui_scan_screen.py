"""
DA-005b-2 scan screen Pilot tests: form, clobber dialog, spawn-to-complete
against a real detached subprocess, and registry reattach from a fresh app.
"""

import time
from pathlib import Path

import pytest
from drive_archaeologist.scanjobs import is_alive, load_jobs, spawn_scan
from drive_archaeologist.tui.app import DriveArchApp
from drive_archaeologist.tui.screens.scan import ClobberDialog, ScanScreen
from drive_archaeologist.tui.screens.survey import SurveyScreen
from textual.widgets import Button, Input, Static

from .test_tui_screens import make_device


@pytest.fixture(autouse=True)
def isolated_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


def make_tree(root: Path, n: int = 10) -> Path:
    root.mkdir(parents=True)
    for i in range(n):
        (root / f"f{i:03}.txt").write_text("x")
    return root


async def wait_for(pilot, predicate, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await pilot.pause(0.2)
    return False


@pytest.mark.asyncio
async def test_form_prefills_output_from_label(tmp_path):
    device = make_device(mountpoint=make_tree(tmp_path / "drive"))
    app = DriveArchApp(device_provider=lambda: [device])
    async with app.run_test() as pilot:
        app.push_screen(ScanScreen(device=device))
        await pilot.pause()
        value = app.screen.query_one("#output-path", Input).value
        assert value.endswith("surveys/Backup Plus/full_scan.jsonl")


@pytest.mark.asyncio
async def test_clobber_dialog_on_existing_output(tmp_path):
    device = make_device(mountpoint=make_tree(tmp_path / "drive"))
    out = tmp_path / "out.jsonl"
    out.write_text("previous catalog\n")
    app = DriveArchApp(device_provider=lambda: [device])
    async with app.run_test() as pilot:
        app.push_screen(ScanScreen(device=device))
        await pilot.pause()
        app.screen.query_one("#output-path", Input).value = str(out)
        app.screen.query_one("#start", Button).press()
        await pilot.pause()
        assert isinstance(app.screen, ClobberDialog)
        app.screen.query_one("#clobber-back", Button).press()
        await pilot.pause()
        assert isinstance(app.screen, ScanScreen)  # back on the form


@pytest.mark.asyncio
async def test_start_scan_runs_detached_to_completion(tmp_path):
    device = make_device(mountpoint=make_tree(tmp_path / "drive", n=12))
    out = tmp_path / "surveys" / "full_scan.jsonl"
    app = DriveArchApp(device_provider=lambda: [device])
    async with app.run_test() as pilot:
        app.push_screen(ScanScreen(device=device))
        await pilot.pause()
        app.screen.query_one("#output-path", Input).value = str(out)
        app.screen.query_one("#start", Button).press()
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ScanScreen)
        assert screen.job is not None

        def complete():
            return "Scan complete" in str(screen.query_one("#scan-counter", Static).render())

        assert await wait_for(pilot, complete), "scan never completed"
        assert len(out.read_text().splitlines()) == 12
        assert screen.query_one("#cancel", Button).disabled  # finished state
        assert load_jobs() == []  # pruned on completion


@pytest.mark.asyncio
async def test_reattach_from_registry_on_fresh_app(tmp_path):
    """A scan spawned outside the app (previous TUI instance) is rediscovered."""
    root = make_tree(tmp_path / "drive", n=8000)
    out = tmp_path / "surveys" / "full_scan.jsonl"
    device = make_device(mountpoint=root)
    job = spawn_scan(root=root, output=out, identity=device.identity, include_hidden=True)
    app = DriveArchApp(device_provider=lambda: [device])
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.screen, ScanScreen)  # auto-attached on top
            assert app.screen.job is not None
            assert app.screen.job.output_jsonl == str(out)
    finally:
        if is_alive(job):
            import os
            import signal

            os.kill(job.pid, signal.SIGTERM)


@pytest.mark.asyncio
async def test_survey_full_scan_button_pushes_scan_screen(tmp_path):
    device = make_device(mountpoint=make_tree(tmp_path / "drive"))
    app = DriveArchApp(device_provider=lambda: [device])
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")  # drives -> survey
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(app.screen, SurveyScreen)
        assert app.screen.query_one("#full-scan", Button).disabled is False
        await pilot.press("f")
        await pilot.pause()
        assert isinstance(app.screen, ScanScreen)
        assert app.screen.total_hint == 10  # survey count feeds the progress bar
