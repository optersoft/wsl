"""Running Windows programs, with and without a UAC prompt.

Everything wslx does to a machine is some other program's job: `wsl.exe`,
`netsh`, `schtasks`, `usbipd`, PowerShell. This module is the one place that
knows how to start them, read what they said, and — for the handful of jobs
Windows will not do for a standard user — ask for elevation.

Two rules hold everywhere below.

**No console windows.** wslx is also a GUI, and a GUI that flashes a black
console box every time it polls a distribution is unusable. Every call passes
`CREATE_NO_WINDOW`.

**Arguments are a list, never a string.** A distribution name is chosen by
whoever registered it, not necessarily by us, and `wsl --list` will happily
hand back a name containing `&`. Concatenating that into a command line —
especially an elevated one — is how a GUI ends up running someone else's
command as administrator. The only place a command *line* is built is
:func:`elevate_script`, which writes the commands to a file we own rather than
passing them through a shell.
"""

from __future__ import annotations

import locale
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

#: Windows process creation flag: no console window for the child.
CREATE_NO_WINDOW = 0x08000000


class RunError(Exception):
    """A program could not be started, or refused to do what was asked."""


@dataclass(frozen=True)
class Result:
    """What a program did: its exit code and what it printed."""

    code: int
    out: str
    err: str

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def message(self) -> str:
        """The line to show a user when this failed.

        `wsl.exe` reports errors on stdout as often as on stderr, so take
        whichever is not empty and keep the first line: the rest is usually a
        usage dump.
        """
        text = self.err.strip() or self.out.strip()
        return text.splitlines()[0] if text else f"exit code {self.code}"


def windows() -> bool:
    return sys.platform == "win32"


def decode(data: bytes) -> str:
    """Decode the output of a Windows console program.

    Three encodings turn up. `wsl.exe` with `WSL_UTF8=1` (which we always set)
    is UTF-8, but older builds and some code paths still emit UTF-16LE —
    recognisable by its interleaved NUL bytes. `netsh`, `schtasks` and friends
    write the console's OEM code page, which on a Spanish or Chinese Windows is
    not UTF-8 and not Latin-1 either.
    """
    if b"\x00" in data:
        return data.decode("utf-16-le", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode(locale.getpreferredencoding(False), errors="replace")


def _flags() -> dict[str, int]:
    return {"creationflags": CREATE_NO_WINDOW} if windows() else {}


def run(
    argv: list[str], *, env: dict[str, str] | None = None, timeout: float | None = None
) -> Result:
    """Run `argv`, capturing its output. Never raises for a non-zero exit."""
    try:
        completed = subprocess.run(  # noqa: S603 - argv is a list, no shell
            argv,
            capture_output=True,
            env=env,
            timeout=timeout,
            check=False,
            **_flags(),
        )
    except FileNotFoundError as exc:
        raise RunError(f"{argv[0]} not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise RunError(f"{argv[0]}: timed out after {timeout:g}s") from exc
    return Result(completed.returncode, decode(completed.stdout), decode(completed.stderr))


def powershell(script: str, *, timeout: float | None = 30.0) -> Result:
    """Run a PowerShell snippet.

    Used for the two questions Windows answers nowhere else: what the physical
    disks are (CIM), and compacting a VHDX (Hyper-V's `Optimize-VHD`). The
    snippet is ours in every case — nothing a user typed is interpolated into
    it without being validated first.
    """
    return run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        timeout=timeout,
    )


def detached(argv: list[str]) -> None:
    """Start a program and do not wait for it.

    For the integrations — a terminal, an editor, Explorer — where the point is
    that the window outlives the call.
    """
    try:
        subprocess.Popen(argv, **_flags())  # noqa: S603 - argv is a list, no shell
    except FileNotFoundError as exc:
        raise RunError(f"{argv[0]} not found") from exc


def elevate(argv: list[str]) -> int:
    """Run `argv` as administrator, waiting for it to finish.

    `ShellExecuteExW` with the `runas` verb is what raises the UAC prompt; a
    subprocess cannot elevate itself any other way. The arguments are joined
    with `subprocess.list2cmdline`, which applies the quoting rules the C
    runtime uses to take them apart again, so a path with a space survives.

    Returns the elevated process's exit code. Declining the prompt raises
    :class:`RunError` rather than looking like a failed command, because it is
    the one failure the user meant.
    """
    if not windows():
        raise RunError("elevation is only available on Windows")

    import ctypes  # noqa: PLC0415 - windows-only, and only on this path
    from ctypes import wintypes  # noqa: PLC0415

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = (
            ("cbSize", wintypes.DWORD),
            ("fMask", ctypes.c_ulong),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hIcon", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        )

    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SEE_MASK_NOASYNC = 0x00000100
    SW_HIDE = 0
    ERROR_CANCELLED = 1223
    INFINITE = 0xFFFFFFFF

    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NOASYNC
    info.lpVerb = "runas"
    info.lpFile = argv[0]
    info.lpParameters = subprocess.list2cmdline(argv[1:])
    info.nShow = SW_HIDE

    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
        error = ctypes.get_last_error() or ctypes.GetLastError()
        if error == ERROR_CANCELLED:
            raise RunError("administrator permission was declined")
        raise RunError(f"could not elevate {argv[0]} (error {error})")

    kernel32 = ctypes.windll.kernel32
    kernel32.WaitForSingleObject(info.hProcess, INFINITE)
    code = wintypes.DWORD()
    kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
    kernel32.CloseHandle(info.hProcess)
    return int(code.value)


def script_text(commands: list[list[str]], log: Path) -> str:
    """The `.cmd` file :func:`elevate_script` runs.

    Split out from it so the quoting can be tested anywhere: this is the one
    function in wslx whose output a shell parses, so it is the one that has to
    be right about a name like `a & shutdown /r`. `list2cmdline` quotes each
    argument, and cmd.exe's parser then sees the `&` inside quotes as text.
    """
    lines = ["@echo off", "chcp 65001 > nul"]
    for command in commands:
        lines.append(f'{subprocess.list2cmdline(command)} >> "{log}" 2>&1')
    return "\r\n".join(lines) + "\r\n"


def elevate_script(commands: list[list[str]], *, name: str = "wslx") -> Result:
    """Run several commands as administrator, in order, and read their output.

    One UAC prompt for the batch — adding a port forwarding rule means a
    `netsh portproxy` and a firewall rule, and two prompts for one button is
    not a thing anyone tolerates.

    The commands go into a `.cmd` file we write ourselves and hand to
    `cmd /c`, instead of being joined with `&` on the command line. Same
    result, but the only string a shell parses is one this module built from
    already-quoted arguments, in a file only this user can write — and the log
    is the only way to see what a window-less elevated process said.
    """
    workspace = Path(tempfile.mkdtemp(prefix=f"{name}-"))
    script = workspace / f"{name}.cmd"
    log = script.with_suffix(".log")
    script.write_text(script_text(commands, log), encoding="utf-8")
    try:
        code = elevate(["cmd.exe", "/c", str(script)])
        output = decode(log.read_bytes()) if log.is_file() else ""
    finally:
        for path in (script, log):
            path.unlink(missing_ok=True)
        workspace.rmdir()
    return Result(code, output, "" if code == 0 else output)
