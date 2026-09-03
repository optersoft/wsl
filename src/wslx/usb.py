"""Handing a USB device to a distribution.

WSL machines do not see USB devices. Nothing in `wsl.exe` changes that: the
kernel they share has no path to the host's USB bus, so the device has to be
handed over the network, by a separate project — `usbipd-win`, which Microsoft
points at in its own documentation and which the tutorial already installs for
the microcontroller exercise.

Two steps, and the order is not optional:

`bind`     detach the device from Windows and share it. Administrator, once
           per device; Windows remembers.
`attach`   give the shared device to a distribution. Standard user, every time
           the device is plugged in or the machine restarts.

The state is read from `usbipd state`, which is JSON, so it is read as JSON —
with the text listing as a fallback for the 3.x releases that had no such
command.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from . import report, wsl
from .run import RunError, elevate_script, run
from .wsl import WslError


@dataclass(frozen=True)
class Device:
    """One USB device as usbipd sees it."""

    busid: str
    description: str
    vid_pid: str = ""
    shared: bool = False
    attached: bool = False

    @property
    def state(self) -> str:
        if self.attached:
            return "Attached"
        return "Shared" if self.shared else "Not shared"


def parse_state(output: str) -> list[Device]:
    """Read `usbipd state`, which is JSON with a `Devices` array.

    A device that is bound has a `PersistedGuid`; one that is attached to a
    client has a `ClientIPAddress`. Devices with no bus id are persisted
    entries for hardware that is currently unplugged, and are not listed.
    """
    try:
        payload = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return []

    devices = []
    for entry in payload.get("Devices", []):
        busid = entry.get("BusId")
        if not busid:
            continue
        devices.append(
            Device(
                busid=busid,
                description=entry.get("Description", ""),
                vid_pid=entry.get("HardwareId", ""),
                shared=bool(entry.get("PersistedGuid")),
                attached=bool(entry.get("ClientIPAddress")),
            )
        )
    return devices


#: A row of `usbipd list`: bus id, vid:pid, description, then a state that may
#: be several words. The description is greedy, so the split is anchored on the
#: known shapes at either end.
_ROW = re.compile(r"^(\d+-\d+)\s+([0-9a-f]{4}:[0-9a-f]{4})\s+(.+?)\s\s+(\S.*)$", re.IGNORECASE)


def parse_list(output: str) -> list[Device]:
    """Read `usbipd list` — the fallback for releases without `state`."""
    devices = []
    for line in output.splitlines():
        match = _ROW.match(line.rstrip())
        if not match:
            continue
        busid, vid_pid, description, state = match.groups()
        state = state.strip().lower()
        devices.append(
            Device(
                busid=busid,
                description=description.strip(),
                vid_pid=vid_pid,
                shared=state != "not shared",
                attached=state.startswith("attached"),
            )
        )
    return devices


def installed() -> bool:
    """Is usbipd-win on this machine?"""
    try:
        return run(["usbipd", "--version"]).ok
    except RunError:
        return False


def require() -> None:
    if not installed():
        raise WslError(
            "usbipd-win is not installed — run "
            "`winget install --exact dorssel.usbipd-win` from an administrator terminal"
        )


def devices() -> list[Device]:
    """Every USB device usbipd knows about."""
    wsl._require_windows()
    require()
    state = run(["usbipd", "state"])
    if state.ok and (parsed := parse_state(state.out)):
        return parsed
    return parse_list(run(["usbipd", "list"]).out)


def device(busid: str) -> Device:
    for found in devices():
        if found.busid == busid:
            return found
    raise WslError(f"{busid}: no such USB device")


def attach(busid: str, name: str | None = None) -> None:
    """Give the device at `busid` to a distribution.

    Binding is what needs administrator rights, and it only needs them once —
    so an unbound device gets bound and attached under a single prompt, and a
    device that is already shared is attached with no prompt at all. That is
    the whole reason to check the state first rather than always elevating.
    """
    wsl._require_windows()
    found = device(busid)
    if name and not wsl.running(name):
        raise WslError(f"{name}: not running — start it before attaching a device")

    attach_command = ["usbipd", "attach", "--wsl", "--busid", busid]
    if name:
        attach_command[3:3] = [f"--distribution={name}"]

    if not found.shared:
        report.say(f"{busid}: sharing and attaching (administrator permission required) ...")
        result = elevate_script(
            [["usbipd", "bind", "--busid", busid], attach_command], name="wslx-usb"
        )
    else:
        report.say(f"{busid}: attaching ...")
        result = run(attach_command)

    if not result.ok:
        raise WslError(f"{busid}: attach failed — {result.message}")
    report.say(f"{busid}: {found.description} attached")


def detach(busid: str) -> None:
    """Take the device back. Windows sees it again immediately."""
    wsl._require_windows()
    require()
    result = run(["usbipd", "detach", "--busid", busid])
    if not result.ok:
        raise WslError(f"{busid}: detach failed — {result.message}")
    report.say(f"{busid}: detached")


def unshare(busid: str) -> None:
    """Undo the binding, so Windows stops offering the device at all."""
    wsl._require_windows()
    require()
    report.say(f"{busid}: unsharing (administrator permission required) ...")
    result = elevate_script([["usbipd", "unbind", "--busid", busid]], name="wslx-usb")
    if not result.ok:
        raise WslError(f"{busid}: unbind failed — {result.message}")
