"""
DA-005a device enumeration tests: lsblk parsing, identity resolution,
hazard badges. All against canned lsblk JSON — no real block devices.
"""

import pytest
from drive_archaeologist.tui.devices import (
    DeviceIdentity,
    DeviceResolutionError,
    list_block_devices,
    resolve_device,
)

# Shaped like real `lsblk --json --bytes` output on the T420 with the
# Seagate BUP Ultra Touch attached (vendor strings space-padded, older
# lsblk "0"/"1" strings for rm/ro on one entry to cover both formats).
LSBLK_FIXTURE = {
    "blockdevices": [
        {
            "name": "sda",
            "path": "/dev/sda",
            "type": "disk",
            "size": 240057409536,
            "label": None,
            "fstype": None,
            "mountpoint": None,
            "vendor": "ATA     ",
            "model": "KINGSTON SA400S37240G",
            "serial": "50026B778384A11D",
            "rm": False,
            "ro": False,
            "fsused": None,
            "fssize": None,
            "children": [
                {
                    "name": "sda2",
                    "path": "/dev/sda2",
                    "type": "part",
                    "size": 52428800000,
                    "label": None,
                    "fstype": "ext4",
                    "mountpoint": "/",
                    "vendor": None,
                    "model": None,
                    "serial": None,
                    "rm": False,
                    "ro": False,
                    "fsused": 30000000000,
                    "fssize": 52428800000,
                },
            ],
        },
        {
            "name": "sdc",
            "path": "/dev/sdc",
            "type": "disk",
            "size": 1000204886016,
            "label": None,
            "fstype": None,
            "mountpoint": None,
            "vendor": "Seagate ",
            "model": "BUP Ultra Touch",
            "serial": "NACAFVGH",
            "rm": "1",
            "ro": "0",
            "fsused": None,
            "fssize": None,
            "children": [
                {
                    "name": "sdc2",
                    "path": "/dev/sdc2",
                    "type": "part",
                    "size": 999994752512,
                    "label": "Backup Plus",
                    "fstype": "ntfs",
                    "mountpoint": None,
                    "vendor": None,
                    "model": None,
                    "serial": None,
                    "rm": "1",
                    "ro": "0",
                    "fsused": None,
                    "fssize": None,
                },
            ],
        },
        {
            "name": "sdd",
            "path": "/dev/sdd",
            "type": "disk",
            "size": 8004304896,
            "label": "FIELDSTICK",
            "fstype": "vfat",
            "mountpoint": None,
            "vendor": "Kingston",
            "model": "DataTraveler",
            "serial": "KING001",
            "rm": True,
            "ro": True,
            "fsused": 9000000000,
            "fssize": 8004304896,
            "children": [],
        },
        {
            "name": "zram0",
            "path": "/dev/zram0",
            "type": "disk",
            "size": 12884901888,
            "label": None,
            "fstype": None,
            "mountpoint": "[SWAP]",
            "vendor": None,
            "model": None,
            "serial": None,
            "rm": False,
            "ro": False,
            "fsused": None,
            "fssize": None,
        },
        {
            "name": "loop0",
            "path": "/dev/loop0",
            "type": "loop",
            "size": 4096,
            "label": None,
            "fstype": None,
            "mountpoint": None,
            "vendor": None,
            "model": None,
            "serial": None,
            "rm": False,
            "ro": True,
            "fsused": None,
            "fssize": None,
        },
    ]
}


@pytest.fixture
def devices():
    return list_block_devices(LSBLK_FIXTURE)


def test_partitions_inherit_disk_identity(devices):
    backup = next(d for d in devices if d.label == "Backup Plus")
    assert backup.vendor == "Seagate"  # trailing pad stripped
    assert backup.serial == "NACAFVGH"
    assert backup.model == "BUP Ultra Touch"
    assert backup.dev_type == "part"


def test_loop_and_zram_devices_excluded(devices):
    names = {d.name for d in devices}
    assert "loop0" not in names
    assert "zram0" not in names


def test_partitionless_disk_listed_directly(devices):
    stick = next(d for d in devices if d.name == "sdd")
    assert stick.dev_type == "disk"
    assert stick.label == "FIELDSTICK"


def test_string_and_bool_flag_formats_both_parse(devices):
    backup = next(d for d in devices if d.label == "Backup Plus")  # "1"/"0" strings
    stick = next(d for d in devices if d.name == "sdd")  # true/false booleans
    assert backup.removable is True and backup.read_only is False
    assert stick.removable is True and stick.read_only is True


def test_hazard_write_locked(devices):
    stick = next(d for d in devices if d.name == "sdd")
    assert any("write-locked" in h for h in stick.hazards())


def test_hazard_used_exceeds_capacity(devices):
    stick = next(d for d in devices if d.name == "sdd")  # fsused 9GB > fssize 8GB
    assert any("probable filesystem corruption" in h for h in stick.hazards())


def test_hazard_unmounted(devices):
    backup = next(d for d in devices if d.label == "Backup Plus")
    assert any("not mounted" in h for h in backup.hazards())
    stick = next(d for d in devices if d.name == "sdd")  # unmounted vfat wording
    assert any("unmounted raw vfat" in h for h in stick.hazards())


def test_mounted_healthy_partition_has_no_hazards(devices):
    root = next(d for d in devices if d.mountpoint == "/")
    assert root.hazards() == []


def test_resolve_by_identity_not_letter(devices):
    identity = DeviceIdentity(vendor="Seagate", serial="NACAFVGH", label="Backup Plus")
    # Simulate a re-plug letter shift: same drive now enumerated as sdb2
    shifted = list_block_devices(LSBLK_FIXTURE)
    target = next(d for d in shifted if d.label == "Backup Plus")
    target.name = "sdb2"
    target.path = "/dev/sdb2"
    resolved = resolve_device(identity, devices=shifted)
    assert resolved.path == "/dev/sdb2"


def test_resolve_unplugged_raises(devices):
    identity = DeviceIdentity(vendor="Gone", serial="XXXX", label="Ghost")
    with pytest.raises(DeviceResolutionError, match="unplugged"):
        resolve_device(identity, devices=devices)


def test_resolve_ambiguous_raises(devices):
    twin_a = next(d for d in devices if d.label == "Backup Plus")
    twin_b = list_block_devices(LSBLK_FIXTURE)[0]
    twin_b.vendor, twin_b.serial, twin_b.label = twin_a.vendor, twin_a.serial, twin_a.label
    with pytest.raises(DeviceResolutionError, match="Ambiguous"):
        resolve_device(twin_a.identity, devices=[twin_a, twin_b])
