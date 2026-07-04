"""
Screen 3 — full scan (DA-005b-2).

The scan itself is a detached `drive-arch scan` subprocess (scanjobs.py);
this screen is only a viewer over it: spawn form -> clobber dialog ->
progress by tailing the output JSONL. Back leaves the scan running — a
fresh TUI instance reattaches through the job registry.
"""

import time
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Checkbox, Footer, Header, Input, ProgressBar, Static

from ...scanjobs import (
    ScanJob,
    cancel_job,
    count_jsonl_lines,
    is_alive,
    is_complete,
    pause_job,
    prune_jobs,
    resume_job,
    spawn_scan,
)
from ..devices import BlockDevice

POLL_SECONDS = 1.0


class ClobberDialog(ModalScreen[str]):
    """Output file already exists: resume it, overwrite it, or back out."""

    def __init__(self, output: Path) -> None:
        super().__init__()
        self.output = output

    def compose(self) -> ComposeResult:
        with Vertical(id="clobber-box"):
            yield Static(
                f"Output already exists:\n{self.output}\n\n"
                "Resume continues the previous scan from its checkpoint; "
                "overwrite discards it.",
                id="clobber-text",
            )
            with Horizontal():
                yield Button("Resume", id="clobber-resume", variant="primary")
                yield Button("Overwrite", id="clobber-overwrite", variant="error")
                yield Button("Back", id="clobber-back")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(
            {"clobber-resume": "resume", "clobber-overwrite": "overwrite"}.get(
                event.button.id or "", "back"
            )
        )


class ScanScreen(Screen):
    """New-scan form (device mode) or live view of a detached job (attach mode)."""

    BINDINGS = [
        Binding("b,escape", "back", "Back (scan keeps running)"),
        Binding("p", "pause_resume", "Pause/Resume"),
        Binding("c", "cancel_scan", "Cancel scan"),
    ]

    def __init__(
        self,
        device: BlockDevice | None = None,
        job: ScanJob | None = None,
        total_hint: int | None = None,
    ) -> None:
        super().__init__()
        assert (device is None) != (job is None), "exactly one of device/job"
        self.device = device
        self.job = job
        self.total_hint = total_hint
        self.paused = False
        self._count = 0
        self._offset = 0
        self._attach_started = time.monotonic()

    # ---------- layout ----------

    def _default_output(self) -> Path:
        label = (self.device.label or self.device.name) if self.device else "scan"
        return Path.home() / "surveys" / label.replace("/", "_") / "full_scan.jsonl"

    def compose(self) -> ComposeResult:
        yield Header()
        owner = self.device if self.device is not None else self.job
        assert owner is not None
        title = owner.identity.describe()
        yield Static(f"Full scan — {title}", id="scan-title")
        if self.device is not None:
            with Vertical(id="scan-form"):
                yield Static("Output catalog path:")
                yield Input(value=str(self._default_output()), id="output-path")
                yield Checkbox("Include hidden/system entries", value=True, id="include-hidden")
                yield Static("Archive depth (0 = don't open archives):")
                yield Input(value="0", id="archive-depth", type="integer")
                with Horizontal():
                    yield Button("Start scan", id="start", variant="primary")
                    yield Button("Back", id="back")
        yield Vertical(id="scan-progress")
        yield Static("", id="command-echo")
        yield Footer()

    def on_mount(self) -> None:
        if self.job is not None:
            self._enter_attached()

    # ---------- new-scan form ----------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.action_back()
        elif event.button.id == "start":
            self._try_start()
        elif event.button.id == "pause-resume":
            self.action_pause_resume()
        elif event.button.id == "cancel":
            self.action_cancel_scan()

    def _form_params(self) -> dict:
        depth_raw = self.query_one("#archive-depth", Input).value or "0"
        return {
            "output": Path(self.query_one("#output-path", Input).value).expanduser(),
            "include_hidden": self.query_one("#include-hidden", Checkbox).value,
            "max_archive_depth": int(depth_raw),
        }

    def _try_start(self) -> None:
        params = self._form_params()
        if params["output"].exists():
            self.app.push_screen(ClobberDialog(params["output"]), self._clobber_decided)
        else:
            self._spawn(force=False)

    def _clobber_decided(self, decision: str | None) -> None:
        if decision == "resume":
            self._spawn(force=False)  # --resume is always on; checkpoint continues
        elif decision == "overwrite":
            self._spawn(force=True)
        # "back": stay on the form so the path can be edited

    def _spawn(self, force: bool) -> None:
        assert self.device is not None and self.device.mountpoint is not None
        params = self._form_params()
        self.job = spawn_scan(
            root=Path(self.device.mountpoint),
            output=params["output"],
            identity=self.device.identity,
            include_hidden=params["include_hidden"],
            max_archive_depth=params["max_archive_depth"],
            force=force,
        )
        self.query_one("#scan-form", Vertical).remove()
        self._enter_attached()

    # ---------- attached view ----------

    def _enter_attached(self) -> None:
        assert self.job is not None
        progress = self.query_one("#scan-progress", Vertical)
        progress.mount(Static("attaching…", id="scan-counter"))
        progress.mount(
            ProgressBar(total=self.total_hint, show_eta=bool(self.total_hint), id="scan-bar")
        )
        progress.mount(
            Horizontal(
                Button("Pause", id="pause-resume"),
                Button("Cancel scan", id="cancel", variant="error"),
                Button("Back (keeps running)", id="back"),
            )
        )
        self.query_one("#command-echo", Static).update("$ " + " ".join(self.job.argv))
        self._attach_started = time.monotonic()
        self.set_interval(POLL_SECONDS, self._poll)
        self._poll()

    def _poll(self) -> None:
        if self.job is None:
            return
        self._count, self._offset = count_jsonl_lines(
            Path(self.job.output_jsonl), self._offset, initial=self._count
        )
        bar = self.query_one("#scan-bar", ProgressBar)
        bar.update(progress=self._count)
        counter = self.query_one("#scan-counter", Static)
        elapsed = time.strftime("%H:%M:%S", time.gmtime(time.monotonic() - self._attach_started))
        total = f"/{self.total_hint:,}" if self.total_hint else ""
        if is_alive(self.job):
            counter.update(f"Scanning… {self._count:,}{total} files · attached {elapsed}")
        elif self.paused:
            counter.update(f"PAUSED — {self._count:,}{total} files · checkpoint saved")
        elif is_complete(self.job):
            counter.update(f"Scan complete — {self._count:,} files -> {self.job.output_jsonl}")
            self._finish()
        else:
            counter.update(
                f"Scan stopped unexpectedly at {self._count:,} files — "
                "press p to resume from checkpoint"
            )
            self.paused = True
            self.query_one("#pause-resume", Button).label = "Resume"

    def _finish(self) -> None:
        prune_jobs()
        self.query_one("#pause-resume", Button).disabled = True
        self.query_one("#cancel", Button).disabled = True

    # ---------- actions ----------

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_pause_resume(self) -> None:
        if self.job is None:
            return
        if not self.paused and is_alive(self.job):
            pause_job(self.job)
            self.paused = True
            self.query_one("#pause-resume", Button).label = "Resume"
        elif self.paused:
            self.job = resume_job(self.job)
            self.paused = False
            self.query_one("#pause-resume", Button).label = "Pause"
            self.notify("Scan resumed from checkpoint")

    def action_cancel_scan(self) -> None:
        if self.job is None or not is_alive(self.job):
            return
        cancel_job(self.job)
        self.paused = True  # partial output + checkpoint kept; resumable
        self.query_one("#pause-resume", Button).label = "Resume"
        self.notify("Scan cancelled — partial catalog and checkpoint kept", severity="warning")
