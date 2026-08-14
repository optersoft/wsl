"""WSL (Windows Subsystem for Linux) provider.

Port of the `box-wsl` crate. WSL only exists on Windows, so every entry point
raises :class:`WslError` on other platforms; the pure helpers (parsing,
decoding, cloud-init rendering) stay importable everywhere so they can be
tested from any machine.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .cloud_init import user_data
from .download import cached
from .paths import cloud_init_file, instance_dir

#: Ubuntu WSL root filesystem image (Noble, current).
ROOTFS_URL = (
    "https://cloud-images.ubuntu.com/wsl/releases/noble/current/"
    "ubuntu-noble-wsl-amd64-wsl.rootfs.tar.gz"
)
ROOTFS_FILE = "ubuntu-noble-wsl-amd64-wsl.rootfs.tar.gz"

#: UID of the `box` user created by cloud-init.
BOX_UID = 1000

#: The `box` user's login name inside the distribution.
BOX_USER = "box"

#: Every value the version column of `wsl --list --verbose` can hold. Used to
#: tell a real table row from a line of localised prose — see `parse_verbose`.
WSL_VERSIONS = frozenset({"1", "2"})


class WslError(Exception):
    """Anything wslx knows how to explain to the user."""


@dataclass(frozen=True)
class Distribution:
    """One row of `wsl --list --verbose`."""

    name: str
    state: str
    version: str
    default: bool = False


def _require_windows() -> None:
    if sys.platform != "win32":
        raise WslError("WSL is only available on Windows")


def decode(data: bytes) -> str:
    """Decode `wsl.exe` output.

    With `WSL_UTF8=1` (which we always set) it is UTF-8, but older builds and
    some code paths still emit UTF-16LE — recognisable by its interleaved NUL
    bytes.
    """
    if b"\x00" in data:
        return data.decode("utf-16-le", errors="replace")
    return data.decode("utf-8", errors="replace")


def _env() -> dict[str, str]:
    import os

    env = dict(os.environ)
    env["WSL_UTF8"] = "1"
    return env


def _capture(*args: str) -> str:
    """Run `wsl.exe` and return its decoded stdout ('' if the call fails)."""
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["wsl", *args],
            capture_output=True,
            env=_env(),
            check=False,
        )
    except OSError:
        return ""
    return decode(result.stdout)


def _spawn(*args: str) -> int:
    """Run `wsl.exe` inheriting stdio and return its exit code."""
    try:
        return subprocess.run(["wsl", *args], env=_env(), check=False).returncode  # noqa: S603
    except FileNotFoundError as exc:
        raise WslError("wsl.exe not found — is WSL installed?") from exc


def _call(*args: str, error: str) -> None:
    """Like :func:`_spawn`, but raise `WslError` on a non-zero exit."""
    if _spawn(*args) != 0:
        raise WslError(error)


def parse_names(output: str) -> list[str]:
    """Parse `wsl --list --quiet` (one distribution name per line)."""
    return [line for line in (raw.strip().strip("\x00") for raw in output.splitlines()) if line]


def parse_verbose(output: str) -> list[Distribution]:
    """Parse `wsl --list --verbose`.

    The header line is localised, so it is identified positionally (it is
    always first) rather than by its text.

    When no distribution is registered, `wsl` exits non-zero and prints prose
    instead of a table ("... no tiene distribuciones instaladas. Para instalar
    las distribuciones, ..."). `_capture` discards the exit code, so that prose
    reaches us and any sentence of three or more words used to parse as a row.
    The version column is the one field that is never localised — it is always
    `1` or `2` — so it is what separates a real row from a translated sentence.
    """
    distributions = []
    for raw in output.splitlines()[1:]:
        line = raw.strip().strip("\x00")
        if not line:
            continue
        default = line.startswith("*")
        fields = line.lstrip("*").split()
        if len(fields) < 3:
            continue
        name, state, version = fields[0], fields[1], fields[2]
        if version not in WSL_VERSIONS:
            continue
        distributions.append(Distribution(name, state, version, default))
    return distributions


def registered(name: str) -> bool:
    """Is `name` a registered WSL distribution?"""
    return name in parse_names(_capture("--list", "--quiet"))


def running(name: str) -> bool:
    """Is `name` currently running?"""
    return name in parse_names(_capture("--list", "--running", "--quiet"))


def list_distributions() -> list[Distribution]:
    """Every registered distribution, whether or not wslx created it."""
    _require_windows()
    return parse_verbose(_capture("--list", "--verbose"))


def managed(name: str) -> bool:
    """Was `name` imported by wslx (i.e. does it own the instance directory)?"""
    return (instance_dir(name) / "ext4.vhdx").is_file()


def create(name: str) -> None:
    """Import a fresh Ubuntu distribution named `name`."""
    _require_windows()
    if registered(name):
        raise WslError(f"{name}: already registered")

    image = cached(ROOTFS_FILE, ROOTFS_URL)

    # WSL picks up cloud-init from %USERPROFILE%\.cloud-init\<distro>.user-data
    config = cloud_init_file(name)
    config.write_text(user_data(name), encoding="utf-8")

    instance = instance_dir(name)
    instance.mkdir(parents=True, exist_ok=True)

    print(f"{name}: importing WSL distribution ...")
    _call(
        "--import",
        name,
        str(instance),
        str(image),
        error=f"{name}: wsl --import failed",
    )


def start(name: str) -> None:
    """Boot `name` and pin its default user to `box`."""
    _require_windows()
    if running(name):
        print(f"{name}: already running")
        return
    if not registered(name):
        raise WslError(f"{name}: not registered")

    print(f"{name}: starting ...", end="", flush=True)
    # Boot as root explicitly. On a first boot cloud-init has not created `box`
    # yet, so uid 1000 has no passwd entry: pinning DefaultUid before this call
    # makes WSL fail to start the systemd user session, which leaves cloud-init
    # degraded and the distribution unseeded. Configure after booting.
    _call(
        "--distribution",
        name,
        "--user",
        "root",
        "--exec",
        "dbus-launch",
        "true",
        error=f"{name}: failed to start",
    )
    print(" done.")

    # The [user] default in wsl.conf is unreliable; force the default UID to
    # 1000 (the `box` user) via the Lxss registry key. WSL binds DefaultUid
    # when an instance launches, so this takes effect from the next launch —
    # the instance booted above stays root. That is why `connect` passes
    # `--user box` explicitly rather than relying on the default.
    set_default_uid(name, BOX_UID)

    # Only distributions wslx imported carry a seed to check; anything else is
    # someone else's and is not supposed to have a box user.
    if managed(name) and not seeded(name):
        raise WslError(
            f"{name}: cloud-init did not apply the wslx seed — uid {BOX_UID} is not "
            f"{BOX_USER!r}, so there is no {BOX_USER} user, hostname or sudo rule. "
            "This is usually a transient failure of cloud-init's WSL datasource; "
            f"run `wslx delete {name}` and create it again."
        )


def seeded(name: str) -> bool:
    """Did cloud-init apply the wslx seed to `name`?

    Not a question `cloud-init status` can answer: `DataSourceWSL`
    intermittently finds no local data, silently falls back to cloud-init's
    built-in config and still finishes with `status: done`. What that fallback
    builds is the Ubuntu image's own `ubuntu` account at uid 1000 — exactly
    where `box` should be — so the name behind uid 1000 is what separates a
    seeded distribution from an unseeded one.

    Runs as root because the whole point is that `box` may not exist.
    """
    _capture("--distribution", name, "--user", "root", "--exec", "cloud-init", "status", "--wait")
    owner = _capture("--distribution", name, "--user", "root", "--exec", "id", "-un", str(BOX_UID))
    return owner.strip() == BOX_USER


def set_default_uid(name: str, uid: int = BOX_UID) -> None:
    """Set `DefaultUid` for `name` under HKCU\\...\\Lxss."""
    _require_windows()
    import winreg  # noqa: PLC0415 - windows-only stdlib module

    lxss_path = r"Software\Microsoft\Windows\CurrentVersion\Lxss"
    try:
        lxss = winreg.OpenKey(winreg.HKEY_CURRENT_USER, lxss_path)
    except OSError as exc:
        raise WslError("opening Lxss registry key") from exc

    with lxss:
        index = 0
        while True:
            try:
                sub = winreg.EnumKey(lxss, index)
            except OSError:
                break
            index += 1
            with winreg.OpenKey(lxss, sub, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
                try:
                    distribution, _ = winreg.QueryValueEx(key, "DistributionName")
                except FileNotFoundError:
                    continue
                if distribution == name:
                    winreg.SetValueEx(key, "DefaultUid", 0, winreg.REG_DWORD, uid)
                    return

    raise WslError(f"{name}: distribution not found in registry")


def stop(name: str) -> None:
    """Terminate `name`."""
    _require_windows()
    if not registered(name):
        raise WslError(f"{name}: not registered")
    _call("--terminate", name, error=f"{name}: failed to terminate")


def delete(name: str) -> None:
    """Unregister `name` and remove the files wslx created for it."""
    _require_windows()
    if not registered(name):
        print(f"{name}: not registered")
        return

    print(f"{name}: removing WSL distribution")
    _call("--unregister", name, error=f"{name}: wsl --unregister failed")

    shutil.rmtree(instance_dir(name), ignore_errors=True)
    _unlink(cloud_init_file(name))


def _unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def connect(name: str, new: bool = False) -> None:
    """Open a shell in `name`, creating and starting it as needed."""
    _require_windows()
    if new:
        create(name)
    if not registered(name):
        raise WslError(f"{name}: not registered")
    if not running(name):
        start(name)

    # The exit code here is the *shell's*, not an error from wsl.exe — a user
    # who types `exit 1` has not made anything go wrong.
    _spawn("--distribution", name, "--cd", "~", "--user", BOX_USER)
