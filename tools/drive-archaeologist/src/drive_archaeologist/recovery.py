"""
Recycle-bin recovery (DA-006): $R/$I pairing and manifest-driven copy-out.

Windows (Vista+) splits every deleted item in $RECYCLE.BIN/<SID>/ into
  $R<rand6>[.ext]  the content — a file, or a directory holding the original
                   tree (members keep their REAL names), and
  $I<rand6>[.ext]  544-byte metadata: version, size, deletion FILETIME, and
                   the original full path (version 1 = Vista/7 fixed 260-wchar
                   field; version 2 = Win10+ length-prefixed).

Recovery is two explicit stages so a human reviews the plan between them:
  pair_recycle_bin()   catalog JSONL -> manifest TSV (dry-run, no copying)
  copy_from_manifest() manifest -> off-drive copy, size-verified, idempotent

Hard rule inherited from the tool: the scanned drive is never modified.
The copy stage refuses any destination outside its --dest-root.

Proven on the DOSTB20150918 excavation (2026-07-04): 14,080 files / 8.02 GiB,
0 orphans, all $I parsed.
"""

import csv
import json
import shutil
import struct
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .scanner import GNSS_CATEGORIES

FILETIME_EPOCH = datetime(1601, 1, 1, tzinfo=UTC)
_V1_PATH_BYTES = 520  # 260 UTF-16 code units, fixed field
_MANIFEST_COLUMNS = (
    "src_path",
    "original_path",
    "deleted_at",
    "size_bytes",
    "category",
    "dest_path",
    "status",
)


class RecycleBinError(Exception):
    """A $I metadata file is missing, truncated, or structurally invalid."""


def parse_dollar_i(path: Path) -> tuple[str, datetime]:
    """Parse a $I file: (original Windows path, deletion time, UTC)."""
    try:
        data = path.read_bytes()
    except OSError as e:
        raise RecycleBinError(f"unreadable $I file {path}: {e}") from e
    if len(data) < 24:
        raise RecycleBinError(f"$I too short ({len(data)} bytes): {path}")
    version, _size, filetime = struct.unpack_from("<qqq", data, 0)
    deleted_at = FILETIME_EPOCH + timedelta(microseconds=filetime / 10)
    if version == 1:
        raw = data[24 : 24 + _V1_PATH_BYTES]
        original = raw.decode("utf-16-le", errors="replace").split("\x00", 1)[0]
    elif version == 2:
        (nchars,) = struct.unpack_from("<i", data, 24)
        if nchars <= 0 or nchars > 32768:
            raise RecycleBinError(f"$I bad path length {nchars}: {path}")
        raw = data[28 : 28 + nchars * 2]
        original = raw.decode("utf-16-le", errors="replace").rstrip("\x00")
    else:
        raise RecycleBinError(f"unknown $I version {version}: {path}")
    if not original:
        raise RecycleBinError(f"$I holds empty original path: {path}")
    return original, deleted_at


def windows_path_to_rel(win_path: str) -> str:
    """'D:\\Backups\\f.22o' -> 'D/Backups/f.22o' (safe to join under a dest root)."""
    p = win_path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        p = p[0].upper() + "/" + p[2:].lstrip("/")
    return p.lstrip("/")


@dataclass
class ManifestRow:
    src_path: Path
    original_path: str
    deleted_at: str
    size_bytes: int
    category: str
    dest_path: Path
    status: str  # "ok" | "orphan"


@dataclass
class PairResult:
    rows: list[ManifestRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    stubs_skipped: int = 0

    @property
    def orphans(self) -> int:
        return sum(1 for r in self.rows if r.status == "orphan")

    @property
    def total_bytes(self) -> int:
        return sum(r.size_bytes for r in self.rows)

    @property
    def dest_collisions(self) -> int:
        return len(self.rows) - len({r.dest_path for r in self.rows})

    def write_manifest(self, path: Path) -> None:
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(_MANIFEST_COLUMNS)
            for r in self.rows:
                writer.writerow(
                    [
                        str(r.src_path),
                        r.original_path,
                        r.deleted_at,
                        r.size_bytes,
                        r.category,
                        str(r.dest_path),
                        r.status,
                    ]
                )


def pair_recycle_bin(
    catalog: Path,
    dest_root: Path,
    categories: set[str] | None = None,
) -> PairResult:
    """Map catalog records inside $RECYCLE.BIN to recovery destinations.

    $I metadata stubs are excluded from the payload (their extensions make
    classifiers mistake them for data — DOSTB lesson). A payload file whose
    $I is missing or unparseable is still recovered, under _orphaned/.
    """
    wanted = GNSS_CATEGORIES if categories is None else categories
    result = PairResult()
    i_cache: dict[Path, tuple[str, datetime] | None] = {}

    with open(catalog, encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            path = record.get("path") or ""
            if record.get("category") not in wanted or "$RECYCLE.BIN" not in path:
                continue
            src = Path(path)
            parts = src.parts
            try:
                bin_idx = parts.index("$RECYCLE.BIN")
                sid_dir = Path(*parts[: bin_idx + 2])
                top_name = parts[bin_idx + 2]
            except (ValueError, IndexError):
                result.errors.append(f"unparseable bin path: {src}")
                continue
            if top_name.startswith("$I"):
                result.stubs_skipped += 1
                continue
            if not top_name.startswith("$R"):
                result.errors.append(f"unexpected non-$R entry: {src}")
                continue
            subpath = Path(*parts[bin_idx + 3 :]) if len(parts) > bin_idx + 3 else None

            i_path = sid_dir / ("$I" + top_name[2:])
            if i_path not in i_cache:
                try:
                    i_cache[i_path] = parse_dollar_i(i_path)
                except RecycleBinError as e:
                    i_cache[i_path] = None
                    result.errors.append(str(e))
            meta = i_cache[i_path]

            if meta is None:
                rel = Path("_orphaned") / top_name
                original, deleted_display, status = "", "", "orphan"
            else:
                original, deleted_at = meta
                rel = Path(windows_path_to_rel(original))
                deleted_display = deleted_at.strftime("%Y-%m-%d %H:%M:%S")
                status = "ok"
            if subpath is not None:
                rel = rel / subpath

            result.rows.append(
                ManifestRow(
                    src_path=src,
                    original_path=original,
                    deleted_at=deleted_display,
                    size_bytes=int(record.get("size_bytes") or 0),
                    category=record["category"],
                    dest_path=dest_root / rel,
                    status=status,
                )
            )
    return result


@dataclass
class CopyStats:
    copied: int = 0
    skipped: int = 0
    failed: int = 0
    copied_bytes: int = 0
    errors: list[str] = field(default_factory=list)


def copy_from_manifest(manifest: Path, dest_root: Path) -> CopyStats:
    """Execute a reviewed manifest. Idempotent; never writes outside dest_root.

    A destination already present with the expected size is skipped, so an
    interrupted run can simply be re-invoked. Every copy is size-verified;
    a mismatch (source changed since cataloging) removes the bad copy and
    counts as failed.
    """
    stats = CopyStats()
    dest_root = dest_root.resolve()
    with open(manifest, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            src = Path(row["src_path"])
            dest = Path(row["dest_path"])
            expected = int(row["size_bytes"])
            if not dest.resolve().is_relative_to(dest_root):
                stats.failed += 1
                stats.errors.append(f"dest outside dest root (refused): {dest}")
                continue
            try:
                if dest.exists() and dest.stat().st_size == expected:
                    stats.skipped += 1
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                got = dest.stat().st_size
                if got != expected:
                    dest.unlink(missing_ok=True)
                    stats.failed += 1
                    stats.errors.append(f"size mismatch {got} != {expected}: {src}")
                    continue
                stats.copied += 1
                stats.copied_bytes += got
            except OSError as e:
                stats.failed += 1
                stats.errors.append(f"copy failed ({e}): {src}")
    return stats
