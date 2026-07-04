"""
Screen 2 — survey (fast wipe/keep triage).

Wraps DeepScanner(stats_only=True) in a thread worker: live counter while
walking, verdict card when done. The scanner runs quiet — the TUI owns the
terminal — and feeds the counter through the on_progress seam.
"""

import time
from datetime import datetime
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static
from textual.worker import Worker, WorkerState

from ...scanner import DeepScanner
from ..devices import BlockDevice
from ..widgets.verdict_card import VerdictCard

# Counter repaints are throttled: a fast walk emits thousands of
# on_progress calls per second, each call_from_thread is a UI message
_COUNTER_MIN_INTERVAL = 0.25

EXPORT_ROOT = Path.home() / "surveys"


class SurveyScreen(Screen):
    BINDINGS = [
        Binding("b,escape", "back", "Back"),
        Binding("f", "full_scan", "Full scan"),
        Binding("h", "resurvey_toggle_hidden", "Toggle hidden + re-survey"),
        Binding("e", "export_summary", "Export summary"),
    ]

    def __init__(self, device: BlockDevice, include_hidden: bool = True) -> None:
        super().__init__()
        self.device = device
        self.include_hidden = include_hidden
        self.scanner: DeepScanner | None = None
        self._last_counter_paint = 0.0

    @property
    def _cli_equivalent(self) -> str:
        flag = "" if self.include_hidden else " --no-include-hidden"
        return f'$ drive-arch survey "{self.device.mountpoint}"{flag}'

    def compose(self) -> ComposeResult:
        yield Header()
        identity = self.device.identity.describe()
        yield Static(f"Survey — {identity} · {self.device.path}", id="survey-title")
        yield Static("Starting survey…", id="survey-counter")
        yield Container(id="verdict-slot")
        with Horizontal(id="survey-buttons"):
            yield Button("Full scan", id="full-scan", disabled=True)
            yield Button(self._hidden_button_label(), id="resurvey-hidden")
            yield Button("Export summary", id="export", disabled=True)
            yield Button("Back", id="back")
        yield Static(self._cli_equivalent, id="command-echo")
        yield Footer()

    def _hidden_button_label(self) -> str:
        return "Re-survey excl. hidden" if self.include_hidden else "Re-survey incl. hidden"

    def on_mount(self) -> None:
        self._start_survey()

    def _start_survey(self) -> None:
        self.query_one("#export", Button).disabled = True
        slot = self.query_one("#verdict-slot", Container)
        slot.remove_children()
        self.query_one("#command-echo", Static).update(self._cli_equivalent)
        self.run_worker(self._run_survey, thread=True, exclusive=True, group="survey")

    def _run_survey(self) -> DeepScanner:
        assert self.device.mountpoint is not None
        scanner = DeepScanner(
            Path(self.device.mountpoint),
            stats_only=True,
            include_hidden=self.include_hidden,
            max_archive_depth=0,
            quiet=True,
            on_progress=self._on_scan_progress,
        )
        scanner.scan()
        return scanner

    def _on_scan_progress(self, count: int, rate: float) -> None:
        # Called from the worker thread — marshal every UI update
        now = time.monotonic()
        if now - self._last_counter_paint < _COUNTER_MIN_INTERVAL:
            return
        self._last_counter_paint = now
        self.app.call_from_thread(self._paint_counter, count, rate)

    def _paint_counter(self, count: int, rate: float) -> None:
        self.query_one("#survey-counter", Static).update(
            f"Surveying… {count:,} files · {rate:,.0f} files/s"
        )

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.group != "survey":
            return
        if event.state == WorkerState.SUCCESS and event.worker.result is not None:
            self._show_verdict(event.worker.result)
        elif event.state == WorkerState.ERROR:
            self.query_one("#survey-counter", Static).update(f"Survey failed: {event.worker.error}")
            self.notify(f"Survey failed: {event.worker.error}", severity="error", timeout=10)

    def _show_verdict(self, scanner: DeepScanner) -> None:
        self.scanner = scanner
        elapsed = time.time() - scanner.start_time
        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))
        self.query_one("#survey-counter", Static).update(
            f"Survey complete — {scanner.file_count:,} files · {elapsed_str}"
        )
        self.query_one("#verdict-slot", Container).mount(VerdictCard(scanner))
        self.query_one("#export", Button).disabled = False
        self.query_one("#full-scan", Button).disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "full-scan":
            self.action_full_scan()
        elif event.button.id == "back":
            self.action_back()
        elif event.button.id == "resurvey-hidden":
            self.action_resurvey_toggle_hidden()
        elif event.button.id == "export":
            self.action_export_summary()

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_full_scan(self) -> None:
        from .scan import ScanScreen

        if self.scanner is None:
            self.notify("Survey still running", severity="warning")
            return
        # Survey's file count = total estimate for the scan progress bar
        self.app.push_screen(ScanScreen(device=self.device, total_hint=self.scanner.file_count))

    def action_resurvey_toggle_hidden(self) -> None:
        self.include_hidden = not self.include_hidden
        self.query_one("#resurvey-hidden", Button).label = self._hidden_button_label()
        self.query_one("#survey-counter", Static).update("Starting survey…")
        self._start_survey()

    def action_export_summary(self) -> None:
        """Write the survey summary to ~/surveys/ — never to the drive itself."""
        if self.scanner is None:
            self.notify("Survey still running — nothing to export yet", severity="warning")
            return
        label = self.device.label or self.device.name or "unlabeled"
        target_dir = EXPORT_ROOT / label.replace("/", "_")
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"tui_survey_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        target.write_text(self._summary_text(), encoding="utf-8")
        self.notify(f"Summary written to {target}", timeout=10)

    def _summary_text(self) -> str:
        assert self.scanner is not None
        stats = self.scanner.stats
        verdict, warnings = self.scanner.survey_verdict()
        lines = [
            f"drive-arch TUI survey — {self.device.identity.describe()} ({self.device.path})",
            f"root: {self.device.mountpoint}",
            f"cli equivalent: {self._cli_equivalent}",
            f"files: {self.scanner.file_count:,} · {stats.total_bytes / (1024**3):.2f} GiB",
            "",
            "categories:",
            *(f"  {category}: {count:,}" for category, count in stats.categories.most_common(12)),
            "",
            "disclosures:",
            *(f"  ⚠ {w}" for w in warnings),
            "",
            f"VERDICT: {verdict}",
        ]
        return "\n".join(lines) + "\n"
