"""
Screen 1 — drive picker.

Lists attached block devices with identity columns and hazard badges.
Selection stores the DeviceIdentity, never the kernel letter; the survey
action re-resolves it so a letter shift between refreshes cannot redirect
the walk to the wrong drive.
"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from ..devices import BlockDevice, DeviceIdentity, DeviceResolutionError, resolve_device

REFRESH_SECONDS = 2.0


def _human_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


class DrivesScreen(Screen):
    # Enter is NOT bound here: the focused DataTable already binds it and
    # emits RowSelected — a screen-level binding would double-fire the push
    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._row_identities: dict[str, DeviceIdentity] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        table: DataTable = DataTable(cursor_type="row", id="drives-table")
        yield table
        yield Static(
            "Enter: survey selected drive · r: refresh · q: quit — "
            "selection tracks drive identity, not device letter",
            id="drives-hint",
        )
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#drives-table", DataTable)
        table.add_columns(
            "Device", "Vendor", "Model", "Size", "Label", "FS", "Mounted at", "RM", "RO", "Hazards"
        )
        self._refresh_devices()
        self.set_interval(REFRESH_SECONDS, self._refresh_devices)

    def _refresh_devices(self) -> None:
        table = self.query_one("#drives-table", DataTable)
        previous_cursor = table.cursor_row
        table.clear()
        self._row_identities.clear()
        try:
            devices = self.app.device_provider()  # type: ignore[attr-defined]
        except Exception as e:
            self.notify(f"Device enumeration failed: {e}", severity="error")
            return
        for index, dev in enumerate(devices):
            row_key = f"dev-{index}"
            self._row_identities[row_key] = dev.identity
            table.add_row(
                dev.path,
                dev.vendor or "—",
                dev.model or "—",
                _human_size(dev.size_bytes),
                dev.label or "—",
                dev.fstype or "—",
                dev.mountpoint or "—",
                "yes" if dev.removable else "no",
                "yes" if dev.read_only else "no",
                "; ".join(dev.hazards()) or "—",
                key=row_key,
            )
        if previous_cursor is not None and table.row_count:
            table.move_cursor(row=min(previous_cursor, table.row_count - 1))

    def action_refresh(self) -> None:
        self._refresh_devices()

    def action_select_drive(self) -> None:
        table = self.query_one("#drives-table", DataTable)
        if not table.row_count:
            return
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        self._survey_identity(self._row_identities[str(row_key.value)])

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        identity = self._row_identities.get(str(event.row_key.value))
        if identity is not None:
            self._survey_identity(identity)

    def _survey_identity(self, identity: DeviceIdentity) -> None:
        try:
            device = resolve_device(
                identity,
                devices=self.app.device_provider(),  # type: ignore[attr-defined]
            )
        except DeviceResolutionError as e:
            self.notify(str(e), severity="error", timeout=8)
            return
        if device.mountpoint is None:
            self.notify(
                f"{identity.describe()} is not mounted — mount it (read-only) first",
                severity="warning",
                timeout=8,
            )
            return
        self._push_survey(device)

    def _push_survey(self, device: BlockDevice) -> None:
        from .survey import SurveyScreen

        self.app.push_screen(SurveyScreen(device))
