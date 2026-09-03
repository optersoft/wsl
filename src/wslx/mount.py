r"""Mounting a real disk, or a disk image, inside WSL.

`/mnt/c` is there from the start, and for a course that is usually enough. It
stops being enough the moment the thing you need is not an NTFS drive Windows
already understands: an ext4 partition on a second disk, a USB stick a Linux
machine wrote, a `.vhdx` you were handed. Windows cannot read any of those, so
copying through `/mnt/c` is not an option — there is nothing on the Windows
side to copy from.

`wsl --mount` hands the whole block device to the shared Linux VM, which mounts
it under `/mnt/wsl/` for every distribution at once. A physical disk needs
administrator rights (it is taken away from Windows while it is mounted); a
disk image does not.

The one thing worth being careful about is which disk: `\\.\PHYSICALDRIVE0` is
usually the one Windows is running from, and it is filtered out here rather
than trusted to whoever is clicking.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from . import report, wsl
from .run import elevate_script, powershell
from .wsl import WslError


@dataclass(frozen=True)
class Disk:
    """A physical disk as Windows lists it."""

    device: str
    model: str
    size: int
    index: int
    interface: str = ""
    system: bool = False

    @property
    def removable(self) -> bool:
        return self.interface.upper() == "USB"


def parse_disks(payload: str, system_index: int | None = None) -> list[Disk]:
    """Read the JSON `Get-CimInstance Win32_DiskDrive | ConvertTo-Json` prints.

    PowerShell's JSON is not quite a list: with a single disk it emits the
    object on its own, and with none it emits nothing at all. Both are normal
    on a laptop, so both are handled here rather than at the call site.
    """
    try:
        parsed = json.loads(payload or "null")
    except json.JSONDecodeError:
        return []
    if parsed is None:
        return []
    if isinstance(parsed, dict):
        parsed = [parsed]

    disks = []
    for entry in parsed:
        index = entry.get("Index")
        if index is None:
            continue
        disks.append(
            Disk(
                device=entry.get("DeviceID", f"\\\\.\\PHYSICALDRIVE{index}"),
                model=(entry.get("Model") or "").strip(),
                size=int(entry.get("Size") or 0),
                index=int(index),
                interface=entry.get("InterfaceType") or "",
                system=index == system_index,
            )
        )
    return disks


def disks(*, include_system: bool = False) -> list[Disk]:
    """The physical disks that can be mounted.

    The disk Windows boots from is left out: `wsl --mount` would take it away
    from the running operating system, and Windows refuses in a way that is
    not always graceful.
    """
    wsl._require_windows()
    boot = powershell(
        "Get-CimInstance Win32_DiskPartition | Where-Object BootPartition | "
        "Select-Object -First 1 -ExpandProperty DiskIndex"
    ).out.strip()
    system_index = int(boot) if boot.isdigit() else None

    listing = powershell(
        "Get-CimInstance Win32_DiskDrive | "
        "Select-Object DeviceID, Model, Size, Index, InterfaceType | ConvertTo-Json"
    ).out
    found = parse_disks(listing, system_index)
    return found if include_system else [disk for disk in found if not disk.system]


def _mount_args(
    target: str,
    *,
    vhd: bool,
    partition: int | None,
    filesystem: str | None,
    name: str | None,
    bare: bool,
    options: str | None,
) -> list[str]:
    args = ["--mount", target]
    if vhd:
        args.append("--vhd")
    if bare:
        # A bare mount hands over the device and mounts nothing: the
        # distribution decides what to do with it. Every other option is about
        # the mount, so they are mutually exclusive.
        args.append("--bare")
        return args
    if partition is not None:
        args += ["--partition", str(int(partition))]
    if filesystem:
        args += ["--type", filesystem]
    if name:
        args += ["--name", name]
    if options:
        args += ["--options", options]
    return args


def mount(
    target: str,
    *,
    vhd: bool = False,
    partition: int | None = None,
    filesystem: str | None = None,
    name: str | None = None,
    bare: bool = False,
    options: str | None = None,
) -> str:
    """Mount `target` — a `\\\\.\\PHYSICALDRIVE<n>` or, with `vhd`, a disk image.

    Returns where it landed. WSL mounts under `/mnt/wsl/<name>`, defaulting the
    name to the device, and the mount is shared: every distribution sees it,
    including ones started afterwards.
    """
    wsl._require_windows()
    args = _mount_args(
        target,
        vhd=vhd,
        partition=partition,
        filesystem=filesystem,
        name=name,
        bare=bare,
        options=options,
    )

    if vhd:
        # A disk image is a file this user already owns, so try it as this user
        # first and only ask for elevation if WSL refuses.
        result = wsl.execute(*args)
        if result.ok:
            return _mounted_at(target, name, bare)
        report.say("mounting needs administrator permission ...")
    else:
        report.say(f"mounting {target} (administrator permission required) ...")

    elevated = elevate_script([["wsl.exe", *args]], name="wslx-mount")
    if not elevated.ok:
        raise WslError(f"{target}: mount failed — {elevated.message}")
    return _mounted_at(target, name, bare)


def unmount(target: str | None = None) -> None:
    """Unmount `target`, or everything WSL has mounted when it is None."""
    wsl._require_windows()
    args = ["--unmount"] + ([target] if target else [])
    result = wsl.execute(*args)
    if result.ok:
        report.say(f"unmounted {target or 'every mounted disk'}")
        return
    elevated = elevate_script([["wsl.exe", *args]], name="wslx-mount")
    if not elevated.ok:
        raise WslError(f"unmount failed — {elevated.message}")
    report.say(f"unmounted {target or 'every mounted disk'}")


def _mounted_at(target: str, name: str | None, bare: bool) -> str:
    if bare:
        return "(bare — the device is attached, nothing is mounted)"
    label = name or target.rsplit("\\", 1)[-1]
    return f"/mnt/wsl/{label}"
