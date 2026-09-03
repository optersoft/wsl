r"""Copying, moving and shrinking a distribution's disk.

`wslx delete` is deliberately brutal — a practice machine is made in the
morning and thrown away in the afternoon. The moment a machine is worth
keeping, though, the only thing standing between it and the next mistake is an
export, and the page this tool is documented on says so and then leaves you to
`wsl --export` by hand.

The four operations here are what that hand work becomes:

`export`    the whole distribution to a tarball, the backup.
`restore`   a tarball back, under any name — which also makes it a *clone*,
            because the name is chosen on the way in, not the way out.
`move`      the disk to another drive, when C: fills up.
`compact`   the disk back down to what is actually used inside it.

Only the last two need administrator rights, and both say so before asking.
"""

from __future__ import annotations

import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from . import info, registry, report, wsl
from .paths import instance_dir
from .run import RunError, elevate_script, powershell
from .wsl import WslError


def export(name: str, path: Path, *, vhd: bool = False) -> None:
    """Write `name` to `path` as a tarball (or a .vhdx with `vhd`).

    The distribution has to be stopped: exporting a running one captures a
    filesystem mid-write, which restores as a machine that fscks on first boot.
    WSL does not enforce it, so wslx does.
    """
    wsl._require_windows()
    if not wsl.registered(name):
        raise WslError(f"{name}: not registered")
    if wsl.running(name):
        report.say(f"{name}: stopping before export ...")
        wsl.stop(name)

    path.parent.mkdir(parents=True, exist_ok=True)
    report.say(f"{name}: exporting to {path.name} ...")
    args = ["--export", name, str(path)]
    if vhd:
        args.append("--vhd")
    result = wsl.execute(*args)
    if not result.ok:
        path.unlink(missing_ok=True)
        raise WslError(f"{name}: export failed — {result.message}")
    report.say(f"{name}: exported {info.human(path.stat().st_size)}")


def restore(name: str, path: Path, *, directory: Path | None = None) -> None:
    """Register `path` as a new distribution called `name`.

    Import is also how you clone: the name and the location are given here, not
    carried in the file, so the same tarball can come back as many machines.

    What the file does *not* carry is which user a session opens as — an
    imported distribution starts as root, every time, which is the surprise the
    tutorial walks people into. wslx puts that back: if the machine turns out
    to have a `box` user, `DefaultUid` is pinned to it exactly as `create`
    would have.
    """
    wsl._require_windows()
    if wsl.registered(name):
        raise WslError(f"{name}: already registered")
    if not path.is_file():
        raise WslError(f"{path}: no such file")

    target = directory or instance_dir(name)
    target.mkdir(parents=True, exist_ok=True)

    report.say(f"{name}: importing {path.name} ...")
    # `export --vhd` writes a disk, not a tarball, and importing one needs a
    # different flag — without it WSL tries to untar a VHDX and says the
    # archive is corrupt, which sends you looking at the wrong thing.
    args = ["--import", name, str(target), str(path)]
    args += ["--vhd"] if path.suffix.lower() == ".vhdx" else ["--version", "2"]
    result = wsl.execute(*args)
    if not result.ok:
        raise WslError(f"{name}: import failed — {result.message}")

    owner = wsl.capture("-d", name, "--user", "root", "--exec", "id", "-un", str(wsl.BOX_UID))
    if owner.strip() == wsl.BOX_USER:
        wsl.set_default_uid(name, wsl.BOX_UID)
    report.say(f"{name}: imported")


def clone(source: str, name: str, *, directory: Path | None = None) -> None:
    """Copy `source` to a second distribution called `name`.

    An export and an import with a temporary file in between, which is all a
    clone is. The temporary file is as large as the machine, so it goes to the
    system temp directory and is removed even when the import fails.
    """
    wsl._require_windows()
    if not wsl.registered(source):
        raise WslError(f"{source}: not registered")
    if wsl.registered(name):
        raise WslError(f"{name}: already registered")

    with tempfile.TemporaryDirectory(prefix="wslx-clone-") as workspace:
        tarball = Path(workspace) / f"{source}.tar"
        export(source, tarball)
        restore(name, tarball, directory=directory)


def move(name: str, directory: Path) -> None:
    """Move `name`'s disk to `directory`.

    Always elevated. WSL 2.7 and newer refuse `--move` for a standard user with
    an access-denied error that names no permission, so asking first is both
    more honest and more likely to work.
    """
    wsl._require_windows()
    entry = _registration(name)
    if wsl.running(name):
        wsl.stop(name)

    directory.mkdir(parents=True, exist_ok=True)
    report.say(f"{name}: moving disk to {directory} (administrator permission required) ...")
    result = elevate_script([["wsl.exe", "--manage", name, "--move", str(directory)]])
    if not result.ok:
        raise WslError(f"{name}: move failed — {result.message}")

    moved = registry.registration(name).base_path
    if moved == entry.base_path:
        raise WslError(f"{name}: move reported success but the disk is still at {entry.base_path}")
    report.say(f"{name}: disk is now at {moved}")


def set_sparse(name: str, sparse: bool = True) -> None:
    """Turn the disk into one that gives space back when the guest frees it.

    A VHDX that is not sparse only grows. WSL calls this unsafe — hence
    `--allow-unsafe`, which it demands — because the conversion rewrites the
    disk, so nothing may be holding it.

    And `wslx stop` is not enough to reach that state, which is the part that
    costs an afternoon: terminating a distribution leaves its disk **attached
    to the virtual machine they all share**, so WSL refuses with "the VHD is
    currently in use" and tells you to run `wsl.exe --shutdown`. Observed on
    Windows 10 22H2 with WSL 2.7.11. So this shuts the whole thing down first,
    and says so, because it stops everyone else's machines too.
    """
    wsl._require_windows()
    _registration(name)
    _detach(name)
    value = "true" if sparse else "false"
    result = wsl.execute("--manage", name, "--set-sparse", value, "--allow-unsafe")
    if not result.ok:
        raise WslError(f"{name}: could not set sparse={value} — {result.message}")
    report.say(f"{name}: sparse disk {'enabled' if sparse else 'disabled'}")


def compact(name: str) -> int:
    """Shrink `name`'s disk to the space actually used inside it.

    Two halves, and skipping either one wastes the other. Inside, `fstrim`
    tells the disk which blocks the filesystem no longer needs; outside, the
    host rewrites the VHDX without them. `Optimize-VHD` does the outside job
    but ships with Hyper-V, which Windows Home does not have, so `diskpart` —
    present on every Windows — is the fallback.

    Returns how many bytes came back.
    """
    wsl._require_windows()
    entry = _registration(name)
    disk = entry.vhdx
    if not disk.is_file():
        raise WslError(f"{name}: no ext4.vhdx at {entry.base_path}")

    # Measured here, before anything runs, because this is the number the user
    # is looking at when they ask for a compaction. Taking it after the trim
    # attributes the operation's own saving to nobody: `fstrim` plus the
    # shutdown can give back tens of megabytes on their own, and then diskpart
    # correctly reports that there is nothing left — so the tool would say it
    # recovered nothing while the file visibly shrank.
    before = disk.stat().st_size

    if wsl.running(name):
        report.say(f"{name}: trimming the filesystem ...")
        wsl.execute("-d", name, "--user", "root", "--exec", "fstrim", "/")
    _detach(name)

    report.say(f"{name}: compacting {info.human(before)} (administrator permission required) ...")
    # Hyper-V's cmdlet is either installed or it is not — retrying that is
    # eleven seconds spent asking the same question. Only diskpart's failures
    # are worth a second look, because those are the ones the shutdown races.
    strategies = ([_optimize_vhd] if _optimize_available() else []) + [_diskpart_compact]
    reasons = []
    for attempt in strategies:
        ok, reason = _retry(attempt, disk)
        if ok:
            break
        reasons.append(reason)
    else:
        raise WslError(f"{name}: could not compact the disk — {'; '.join(reasons)}")

    # Windows serves a file's size from a directory entry it caches for about
    # a second, so asking straight after diskpart detaches the disk returns
    # the size it had before — and the tool reports recovering nothing while
    # the file on disk is visibly smaller.
    time.sleep(2)
    saved = before - disk.stat().st_size
    if saved <= 0:
        report.say(f"{name}: nothing left to recover — the disk is already as small as it can be")
        return 0
    report.say(f"{name}: recovered {info.human(saved)}")
    return saved


def _retry(attempt: Callable[[Path], tuple[bool, str]], disk: Path) -> tuple[bool, str]:
    """Try a compaction strategy a few times, a few seconds apart.

    `wsl --shutdown` returns before the virtual machine has actually let go of
    the disk, and the failure that follows is indistinguishable from "this
    strategy does not work here": diskpart attaches the VHDX, is told the file
    is in use, and exits. Observed on Windows 10 22H2 — the same diskpart
    script run by hand a couple of seconds later compacts the disk fine.
    """
    reason = ""
    for delay in (0, 3, 8):
        if delay:
            time.sleep(delay)
        ok, reason = attempt(disk)
        if ok:
            return True, reason
    return False, reason


def _optimize_available() -> bool:
    """Is Hyper-V's `Optimize-VHD` here? It is absent on Windows Home."""
    return bool(powershell("Get-Command Optimize-VHD -ErrorAction SilentlyContinue").out.strip())


def _optimize_vhd(disk: Path) -> tuple[bool, str]:
    """Hyper-V's compaction — faster than diskpart when it exists."""
    script = f"Optimize-VHD -Path '{disk}' -Mode Full"
    command = ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
    result = elevate_script([command])
    return result.ok, f"Optimize-VHD said: {result.message}"


def _diskpart_compact(disk: Path) -> tuple[bool, str]:
    r"""diskpart's compaction, which every Windows has.

    diskpart reads a script rather than arguments, so it gets its own file:
    attach the disk read-only (so nothing can write while it is rewritten),
    compact, detach.
    """
    with tempfile.TemporaryDirectory(prefix="wslx-compact-") as workspace:
        script = Path(workspace) / "compact.txt"
        script.write_text(
            "\r\n".join(
                [
                    f'select vdisk file="{disk}"',
                    "attach vdisk readonly",
                    "compact vdisk",
                    "detach vdisk",
                    "exit",
                ]
            )
            + "\r\n",
            encoding="ascii",
        )
        try:
            result = elevate_script([["diskpart", "/s", str(script)]])
        except RunError as exc:
            return False, f"diskpart could not be run: {exc}"
        return result.ok, f"diskpart said: {result.tail or result.message}"


def _detach(name: str) -> None:
    """Get the disk out of WSL's hands.

    `wsl --terminate` stops a distribution; it does not give the disk back.
    The lightweight virtual machine keeps the VHDX attached until *it* stops,
    and anything that rewrites the file — compaction, the sparse conversion —
    fails while that is true, with an error naming a lock and no owner.
    """
    if wsl.running(name):
        wsl.stop(name)
    report.say("stopping WSL entirely — the disk stays attached to the shared VM until it stops")
    wsl.execute("--shutdown")


def set_default(name: str) -> None:
    """Make `name` the distribution a bare `wsl` command opens."""
    wsl._require_windows()
    if not wsl.registered(name):
        raise WslError(f"{name}: not registered")
    result = wsl.execute("--set-default", name)
    if not result.ok:
        raise WslError(f"{name}: could not set as default — {result.message}")
    report.say(f"{name}: is now the default distribution")


def shutdown() -> None:
    """Stop every distribution and the virtual machine they share.

    Stopping the last distribution is not the same as this: the lightweight VM
    stays up, and so does the memory it took. This is what gives it back.
    """
    wsl._require_windows()
    result = wsl.execute("--shutdown")
    if not result.ok:
        raise WslError(f"could not shut WSL down — {result.message}")
    report.say("WSL is shut down")


def _registration(name: str) -> registry.Registration:
    try:
        return registry.registration(name)
    except registry.RegistryError as exc:
        raise WslError(str(exc)) from exc
