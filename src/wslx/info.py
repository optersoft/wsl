"""What a distribution is: where its disk is, how full it is, what IP it has.

Three different places answer these, and none of them answers more than one.
The registry knows where the disk lives; the file system knows how big it has
grown; only the distribution itself, from the inside, knows how much of that is
actually in use or what address it is reachable at.

The parsers are the testable part and are kept pure — every one of them takes
the text a command printed and returns a value, so the whole module can be
exercised from a Mac that has never seen WSL.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import registry, wsl
from .run import windows

#: Windows file attribute marking a sparse file.
FILE_ATTRIBUTE_SPARSE_FILE = 0x00000200


@dataclass(frozen=True)
class Usage:
    """Disk usage inside a distribution, in bytes."""

    total: int
    used: int
    free: int

    @property
    def percent(self) -> int:
        return round(100 * self.used / self.total) if self.total else 0


@dataclass(frozen=True)
class Info:
    """Everything wslx can say about one distribution without changing it."""

    name: str
    version: int
    default: bool
    running: bool
    managed: bool
    from_store: bool
    base_path: Path | None
    vhdx: Path | None
    vhdx_size: int
    sparse: bool
    default_uid: int
    release: str | None = None
    address: str | None = None
    usage: Usage | None = None


def parse_df(output: str) -> Usage | None:
    """Read `df -B1 /` — the root filesystem's size, used and available bytes.

    The header is in English on any distribution wslx creates, but it does get
    translated, so the row is found positionally (the last non-empty line) and
    the columns by position within it, never by name.
    """
    rows = [line.split() for line in output.splitlines() if line.strip()]
    for fields in reversed(rows):
        if len(fields) >= 4 and fields[1].isdigit() and fields[2].isdigit() and fields[3].isdigit():
            return Usage(total=int(fields[1]), used=int(fields[2]), free=int(fields[3]))
    return None


def parse_os_release(output: str) -> str | None:
    """Pull `PRETTY_NAME` out of /etc/os-release."""
    for line in output.splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "PRETTY_NAME":
            return value.strip().strip('"')
    return None


#: An `inet` line from `ip -4 addr show`, minus its prefix length.
_INET = re.compile(r"^\s*inet\s+(\d+\.\d+\.\d+\.\d+)/\d+")


def parse_addresses(output: str) -> list[str]:
    """Every IPv4 address in `ip -4 addr show`, loopback dropped.

    A distribution has at least `lo` and `eth0`, and in mirrored networking
    mode it also carries the host's addresses. Order is kept: the first
    non-loopback address is the one to show.
    """
    found = [match.group(1) for line in output.splitlines() if (match := _INET.match(line))]
    return [address for address in found if not address.startswith("127.")]


def is_sparse(path: Path) -> bool:
    """Is this file sparse — does it give space back when the guest frees it?

    A non-sparse VHDX only ever grows: delete 10 GB inside the distribution and
    the file on Windows stays exactly as large as it was. Windows records that
    as a file attribute, so the answer costs one API call and no elevation.
    """
    if not windows():
        return False
    import ctypes  # noqa: PLC0415 - windows-only

    attributes = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    if attributes == 0xFFFFFFFF:  # INVALID_FILE_ATTRIBUTES
        return False
    return bool(attributes & FILE_ATTRIBUTE_SPARSE_FILE)


def release(name: str) -> str | None:
    """The distribution's own description of itself, from /etc/os-release."""
    return parse_os_release(wsl.capture("-d", name, "--exec", "cat", "/etc/os-release"))


def address(name: str) -> str | None:
    """The distribution's IPv4 address, or None if it is not up.

    Only asks a running distribution: `wsl -d name --exec` on a stopped one
    boots it, and a listing that silently starts every machine it displays
    would be a surprising thing for a list to do.
    """
    if not wsl.running(name):
        return None
    addresses = parse_addresses(wsl.capture("-d", name, "--exec", "ip", "-4", "addr", "show"))
    return addresses[0] if addresses else None


def usage(name: str) -> Usage | None:
    """Disk usage inside `name`, or None if it is not running."""
    if not wsl.running(name):
        return None
    return parse_df(wsl.capture("-d", name, "--exec", "df", "-B1", "/"))


def info(name: str, *, inside: bool = False) -> Info:
    """Collect what is known about `name`.

    `inside` decides whether the distribution is asked anything: with it False
    this is registry and file-system work only, which is fast and works on a
    stopped machine. The list view uses that; the detail view asks for more.
    """
    entry = None
    try:
        entry = registry.registration(name)
    except registry.RegistryError:
        pass

    vhdx = entry.vhdx if entry and entry.version == 2 else None
    if vhdx is not None and not vhdx.is_file():
        vhdx = None

    collected = Info(
        name=name,
        version=entry.version if entry else 2,
        default=registry.default_name() == name,
        running=wsl.running(name),
        managed=wsl.managed(name),
        from_store=entry.from_store if entry else False,
        base_path=entry.base_path if entry else None,
        vhdx=vhdx,
        vhdx_size=vhdx.stat().st_size if vhdx else 0,
        sparse=is_sparse(vhdx) if vhdx else False,
        default_uid=entry.default_uid if entry else 0,
    )
    if not inside or not collected.running:
        return collected

    from dataclasses import replace  # noqa: PLC0415 - only needed on this path

    return replace(collected, release=release(name), address=address(name), usage=usage(name))


def human(size: float) -> str:
    """Bytes as a human reads them. Sizes here run from megabytes to tens of gigabytes."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit in ("B", "KB") else f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"
