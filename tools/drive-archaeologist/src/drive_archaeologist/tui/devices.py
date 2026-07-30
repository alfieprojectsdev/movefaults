"""
Block-device enumeration and identity resolution for the TUI drive picker.

Selection safety rule (DA-005): a device is identified by vendor+serial+label,
NEVER by its kernel letter. Device letters shift when drives are re-plugged
(the sdc/sdd near-miss, 2026-07-03) — every action re-resolves the identity
against a fresh enumeration and refuses ambiguous or vanished matches.
"""

import json
import subprocess
from dataclasses import dataclass

LSBLK_COLUMNS = (
    "NAME,PATH,TYPE,SIZE,LABEL,FSTYPE,MOUNTPOINT,VENDOR,MODEL,SERIAL,RM,RO,FSUSED,FSSIZE"
)


class DeviceResolutionError(Exception):
    """The stored identity no longer resolves to exactly one attached device."""


@dataclass(frozen=True)
class DeviceIdentity:
    """What a drive IS, independent of where the kernel parked it."""

    vendor: str | None
    serial: str | None
    label: str | None

    def describe(self) -> str:
        return " · ".join(p for p in (self.vendor, self.serial, self.label) if p) or "(no identity)"


@dataclass
class BlockDevice:
    name: str  # kernel name, e.g. "sdc1" — display only, never used for matching
    path: str  # /dev/sdc1
    dev_type: str  # "disk" or "part"
    size_bytes: int
    label: str | None
    fstype: str | None
    mountpoint: str | None
    vendor: str | None  # inherited from parent disk for partitions
    model: str | None
    serial: str | None
    removable: bool
    read_only: bool
    fsused_bytes: int | None
    fssize_bytes: int | None

    @property
    def identity(self) -> DeviceIdentity:
        return DeviceIdentity(vendor=self.vendor, serial=self.serial, label=self.label)

    def hazards(self) -> list[str]:
        """Field-learned warning badges shown in the picker."""
        found = []
        if self.read_only:
            found.append("write-locked (RO=1) — controller is read-only, forever")
        if (
            self.fsused_bytes is not None
            and self.fssize_bytes is not None
            and self.fsused_bytes > self.fssize_bytes
        ):
            found.append("used > capacity — probable filesystem corruption")
        if self.mountpoint is None:
            if self.fstype == "vfat":
                found.append("unmounted raw vfat")
            else:
                found.append("not mounted — survey unavailable")
        return found


def _clean(value: object) -> str | None:
    """lsblk pads VENDOR/MODEL with spaces and uses null/empty for absent."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_bool(value: object) -> bool:
    # lsblk JSON emits true/false on modern versions, "1"/"0" strings on older ones
    if isinstance(value, bool):
        return value
    return str(value).strip() in ("1", "true")


def _to_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value))
    except ValueError:
        return None


def _run_lsblk() -> dict:
    result = subprocess.run(
        ["lsblk", "--json", "--bytes", "-o", LSBLK_COLUMNS],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    parsed: dict = json.loads(result.stdout)
    return parsed


def _device_from_entry(entry: dict, parent: dict | None = None) -> BlockDevice:
    inherit = parent or {}
    return BlockDevice(
        name=str(entry.get("name", "")),
        path=str(entry.get("path") or f"/dev/{entry.get('name', '')}"),
        dev_type=str(entry.get("type", "")),
        size_bytes=_to_int(entry.get("size")) or 0,
        label=_clean(entry.get("label")),
        fstype=_clean(entry.get("fstype")),
        mountpoint=_clean(entry.get("mountpoint")),
        vendor=_clean(entry.get("vendor")) or _clean(inherit.get("vendor")),
        model=_clean(entry.get("model")) or _clean(inherit.get("model")),
        serial=_clean(entry.get("serial")) or _clean(inherit.get("serial")),
        removable=_to_bool(entry.get("rm")),
        read_only=_to_bool(entry.get("ro")),
        fsused_bytes=_to_int(entry.get("fsused")),
        fssize_bytes=_to_int(entry.get("fssize")),
    )


def list_block_devices(lsblk_data: dict | None = None) -> list[BlockDevice]:
    """Flatten lsblk output into scannable candidates.

    Partitions are the scan targets (they carry the filesystem); they inherit
    vendor/model/serial from their parent disk. Disks appear themselves only
    when they have no partitions (superfloppy-formatted sticks). Loop, zram,
    and rom devices are noise, not drives.
    """
    data = lsblk_data if lsblk_data is not None else _run_lsblk()
    devices: list[BlockDevice] = []
    for disk in data.get("blockdevices", []):
        if disk.get("type") not in (None, "disk"):
            continue
        if str(disk.get("name", "")).startswith(("zram", "ram")):
            continue
        children = disk.get("children") or []
        parts = [c for c in children if c.get("type") == "part"]
        if parts:
            devices.extend(_device_from_entry(part, parent=disk) for part in parts)
        else:
            devices.append(_device_from_entry(disk))
    return devices


def resolve_device(
    identity: DeviceIdentity, devices: list[BlockDevice] | None = None
) -> BlockDevice:
    """Re-resolve an identity against a fresh enumeration.

    Raises DeviceResolutionError unless exactly one attached device matches —
    a shifted device letter must never silently redirect an action.
    """
    candidates = devices if devices is not None else list_block_devices()
    matches = [d for d in candidates if d.identity == identity]
    if not matches:
        raise DeviceResolutionError(
            f"No attached device matches {identity.describe()} — was it unplugged?"
        )
    if len(matches) > 1:
        paths = ", ".join(d.path for d in matches)
        raise DeviceResolutionError(
            f"Ambiguous identity {identity.describe()} matches multiple devices: {paths}"
        )
    return matches[0]
