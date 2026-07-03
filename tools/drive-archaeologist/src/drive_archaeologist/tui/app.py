"""
Textual TUI entry point (DA-005a).

The TUI wraps the funnel: pick drive -> survey -> (later phases) scan ->
explore -> act. Hard rule: read-only toward scanned drives — nothing here
ever writes to, moves, or deletes drive contents.
"""

from collections.abc import Callable

from textual.app import App

from .devices import BlockDevice, list_block_devices
from .screens.drives import DrivesScreen


class DriveArchApp(App):
    """drive-archaeologist interactive TUI."""

    TITLE = "drive-arch"
    CSS_PATH = "app.tcss"

    def __init__(
        self,
        device_provider: Callable[[], list[BlockDevice]] | None = None,
    ):
        super().__init__()
        # Injectable so tests (and future udev sources) can swap lsblk out
        self.device_provider = device_provider or list_block_devices

    def on_mount(self) -> None:
        self.push_screen(DrivesScreen())


def run_tui() -> None:
    DriveArchApp().run()
