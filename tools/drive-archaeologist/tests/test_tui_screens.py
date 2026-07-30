"""
DA-005a TUI tests: headless Pilot runs of the drive picker and survey
screens against fake devices and tmp_path trees. No real block devices,
no real terminal.
"""

import pytest
from drive_archaeologist.tui.app import DriveArchApp
from drive_archaeologist.tui.devices import BlockDevice
from drive_archaeologist.tui.screens.drives import DrivesScreen
from drive_archaeologist.tui.screens.survey import SurveyScreen
from drive_archaeologist.tui.widgets.verdict_card import VerdictCard
from textual.widgets import Button, DataTable, Static


def make_device(mountpoint=None, label="Backup Plus", read_only=False):
    return BlockDevice(
        name="sdc2",
        path="/dev/sdc2",
        dev_type="part",
        size_bytes=999_994_752_512,
        label=label,
        fstype="ntfs",
        mountpoint=str(mountpoint) if mountpoint else None,
        vendor="Seagate",
        model="BUP Ultra Touch",
        serial="NACAFVGH",
        removable=True,
        read_only=read_only,
        fsused_bytes=None,
        fssize_bytes=None,
    )


@pytest.fixture
def gnss_tree(tmp_path):
    root = tmp_path / "drive"
    root.mkdir()
    (root / "ALGO0010.22O").write_text("obs")
    (root / "notes.txt").write_text("field notes")
    return root


@pytest.mark.asyncio
async def test_drive_picker_lists_devices_with_hazards(tmp_path):
    mounted = make_device(mountpoint=tmp_path)
    locked = make_device(mountpoint=None, label="FIELDSTICK", read_only=True)
    app = DriveArchApp(device_provider=lambda: [mounted, locked])
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, DrivesScreen)
        table = app.screen.query_one("#drives-table", DataTable)
        assert table.row_count == 2
        rows = [table.get_row_at(i) for i in range(table.row_count)]
        hazard_cells = " | ".join(str(row[-1]) for row in rows)
        assert "write-locked" in hazard_cells
        assert "not mounted" in hazard_cells


@pytest.mark.asyncio
async def test_selecting_mounted_drive_runs_survey_to_verdict(gnss_tree):
    device = make_device(mountpoint=gnss_tree)
    app = DriveArchApp(device_provider=lambda: [device])
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")  # DataTable RowSelected -> survey push
        await pilot.pause()
        assert isinstance(app.screen, SurveyScreen)
        await app.workers.wait_for_complete()
        await pilot.pause()
        card = app.screen.query_one(VerdictCard)
        banner = card.query_one("#verdict-banner", Static)
        assert "DO NOT wipe" in str(banner.render())
        assert banner.has_class("verdict-keep")
        counter = app.screen.query_one("#survey-counter", Static)
        assert "Survey complete" in str(counter.render())


@pytest.mark.asyncio
async def test_selecting_unmounted_drive_stays_on_picker():
    device = make_device(mountpoint=None)
    app = DriveArchApp(device_provider=lambda: [device])
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, DrivesScreen)


@pytest.mark.asyncio
async def test_safe_tree_gets_wipe_candidate_verdict(tmp_path):
    root = tmp_path / "drive"
    root.mkdir()
    (root / "film.mkv").write_bytes(b"m" * 100)
    device = make_device(mountpoint=root)
    app = DriveArchApp(device_provider=lambda: [device])
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        banner = app.screen.query_one("#verdict-banner", Static)
        assert "safe-to-wipe candidate" in str(banner.render())
        assert banner.has_class("verdict-wipe-candidate")


@pytest.mark.asyncio
async def test_export_writes_summary_off_drive(gnss_tree, tmp_path, monkeypatch):
    import drive_archaeologist.tui.screens.survey as survey_module

    export_root = tmp_path / "exports"
    monkeypatch.setattr(survey_module, "EXPORT_ROOT", export_root)
    device = make_device(mountpoint=gnss_tree)
    app = DriveArchApp(device_provider=lambda: [device])
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        export_button = app.screen.query_one("#export", Button)
        assert export_button.disabled is False
        await pilot.press("e")
        await pilot.pause()
        written = list(export_root.rglob("tui_survey_*.txt"))
        assert len(written) == 1
        content = written[0].read_text()
        assert "DO NOT wipe" in content
        assert "drive-arch survey" in content  # CLI equivalent echoed
        # export lands under the drive LABEL dir, never on the drive itself
        assert str(gnss_tree) not in str(written[0])


@pytest.mark.asyncio
async def test_back_returns_to_picker(gnss_tree):
    device = make_device(mountpoint=gnss_tree)
    app = DriveArchApp(device_provider=lambda: [device])
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(app.screen, SurveyScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, DrivesScreen)
