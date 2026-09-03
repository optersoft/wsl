r"""What Windows records about each distribution.

`wsl --list --verbose` gives you a name, a state and a version, and that is
all it gives you. Everything else a manager needs — where the disk actually
is, which user a session opens as, whether the distribution came from the
Store — lives under

    HKCU\Software\Microsoft\Windows\CurrentVersion\Lxss

one subkey per distribution, named by a GUID. The name you know it by is a
value inside, so finding a distribution means walking every subkey. The parent
key's `DefaultDistribution` holds the GUID of the default one.

Reading it is not a trick: it is where `wsl.exe` itself keeps this, and it is
the only way to answer "where is this machine's disk" without asking the
distribution to boot first.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .run import windows

LXSS = r"Software\Microsoft\Windows\CurrentVersion\Lxss"


class RegistryError(Exception):
    """The Lxss key could not be read, or holds no such distribution."""


@dataclass(frozen=True)
class Registration:
    """One distribution as Windows has it written down."""

    guid: str
    name: str
    base_path: Path
    version: int
    default_uid: int
    flags: int
    package_family_name: str | None

    @property
    def from_store(self) -> bool:
        """Did this come from the Microsoft Store?

        Store distributions carry the package family name of the app that
        installed them; an imported one has no package behind it.
        """
        return bool(self.package_family_name)

    @property
    def vhdx(self) -> Path:
        """The virtual disk. WSL 2 always names it `ext4.vhdx`."""
        return self.base_path / "ext4.vhdx"


def _clean(path: str) -> Path:
    r"""Drop the `\\?\` prefix Windows stores on the install location.

    It is the extended-length path syntax; every Python file API accepts the
    plain path, and showing `\\?\C:\...` to a user is just noise.
    """
    return Path(path[4:] if path.startswith("\\\\?\\") else path)


def _open():  # noqa: ANN202 - winreg types only exist on Windows
    import winreg  # noqa: PLC0415 - windows-only stdlib module

    try:
        return winreg.OpenKey(winreg.HKEY_CURRENT_USER, LXSS)
    except OSError as exc:
        raise RegistryError("cannot open the Lxss registry key — is WSL installed?") from exc


def _value(key, name: str, default=None):  # noqa: ANN001, ANN202 - winreg handles
    import winreg  # noqa: PLC0415

    try:
        return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return default


def registrations() -> list[Registration]:
    """Every distribution registered for the current user."""
    if not windows():
        return []

    import winreg  # noqa: PLC0415

    found = []
    with _open() as lxss:
        index = 0
        while True:
            try:
                guid = winreg.EnumKey(lxss, index)
            except OSError:
                break
            index += 1
            with winreg.OpenKey(lxss, guid) as key:
                name = _value(key, "DistributionName")
                if not name:
                    continue
                found.append(
                    Registration(
                        guid=guid,
                        name=name,
                        base_path=_clean(_value(key, "BasePath", "")),
                        version=int(_value(key, "Version", 2) or 2),
                        default_uid=int(_value(key, "DefaultUid", 0) or 0),
                        flags=int(_value(key, "Flags", 0) or 0),
                        package_family_name=_value(key, "PackageFamilyName"),
                    )
                )
    return found


def registration(name: str) -> Registration:
    """The registration for `name`."""
    for entry in registrations():
        if entry.name == name:
            return entry
    raise RegistryError(f"{name}: not in the registry")


def default_name() -> str | None:
    """The name of the default distribution, or None if there is none."""
    if not windows():
        return None
    with _open() as lxss:
        guid = _value(lxss, "DefaultDistribution")
    if not guid:
        return None
    for entry in registrations():
        if entry.guid == guid:
            return entry.name
    return None


def set_default_uid(name: str, uid: int) -> None:
    """Set which user a session opens as.

    WSL reads `DefaultUid` when an instance launches, so this takes effect from
    the next launch, not the running one.
    """
    import winreg  # noqa: PLC0415

    entry = registration(name)
    with _open() as lxss, winreg.OpenKey(lxss, entry.guid, 0, winreg.KEY_WRITE) as key:
        winreg.SetValueEx(key, "DefaultUid", 0, winreg.REG_DWORD, uid)
