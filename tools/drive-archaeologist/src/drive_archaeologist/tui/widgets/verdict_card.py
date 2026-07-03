"""
Survey verdict card (screen 2 payload): category table, disclosure block,
color-coded verdict banner. Color-blind safe — every color state carries a
text label, the color is reinforcement only.
"""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Static

from ...scanner import DeepScanner


class VerdictCard(Vertical):
    def __init__(self, scanner: DeepScanner, top: int = 12) -> None:
        super().__init__()
        self.scanner = scanner
        self.top = top

    def compose(self) -> ComposeResult:
        with Horizontal(id="verdict-tables"):
            yield DataTable(id="category-table", cursor_type="none")
            yield Static(self._disclosure_text(), id="disclosures")
        yield Static(self._banner_text(), id="verdict-banner")

    def on_mount(self) -> None:
        table = self.query_one("#category-table", DataTable)
        table.add_columns("Category", "Files", "Top extensions")
        stats = self.scanner.stats
        for category, count in stats.categories.most_common(self.top):
            exts = [
                e
                for e, _ in stats.extensions.most_common()
                if self.scanner.classifier.classify_by_ext(e) == category
            ][:4]
            table.add_row(category, f"{count:,}", " ".join(exts))
        banner = self.query_one("#verdict-banner", Static)
        banner.add_class(self._banner_class())

    def _disclosure_text(self) -> str:
        _, warnings = self.scanner.survey_verdict()
        lines = [f"⚠ {w}" for w in warnings]
        if self.scanner.include_hidden:
            lines.append("✓ hidden/system entries included")
        if not self.scanner.stats.corrupt_entries and not self.scanner.stats.metadata_inconsistent:
            lines.append("✓ no corruption flags")
        return "\n".join(lines)

    def _banner_text(self) -> str:
        verdict, _ = self.scanner.survey_verdict()
        stats = self.scanner.stats
        total_gib = stats.total_bytes / (1024**3)
        return (
            f"VERDICT: {verdict}\n{self.scanner.file_count:,} files · {total_gib:.2f} GiB surveyed"
        )

    def _banner_class(self) -> str:
        stats = self.scanner.stats
        if stats.gnss_files:
            return "verdict-keep"
        if stats.metadata_inconsistent:
            return "verdict-unreliable"
        return "verdict-wipe-candidate"
