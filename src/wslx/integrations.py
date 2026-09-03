r"""Opening a distribution in the things you actually work in.

Three doors, and each is one command that nobody remembers:

Explorer      `\\wsl.localhost\<name>` — the distribution's filesystem as a
              network share, drag and drop included.
Terminal      a new window already inside the machine, in a chosen directory.
VS Code       the editor running *in* the distribution over Remote-WSL, so the
              terminal, the interpreter and the file paths are all Linux ones.

None of this is privileged and none of it is clever; it is worth having only
because typing it correctly every time is not free.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess

from . import wsl
from .run import detached
from .wsl import WslError

#: The modern name for the share. `\\wsl$\<name>` still resolves, but it is
#: the legacy spelling and Explorer's own address bar shows this one.
SHARE = "\\\\wsl.localhost"


def share(name: str, path: str = "") -> str:
    r"""The UNC path for `path` inside `name`."""
    inside = path.strip("/").replace("/", "\\")
    return f"{SHARE}\\{name}" + (f"\\{inside}" if inside else "")


def explorer(name: str, path: str = "") -> None:
    """Open a distribution's filesystem in Explorer."""
    wsl._require_windows()
    detached(["explorer.exe", share(name, path)])


def terminal(name: str, directory: str = "~", env: dict[str, str] | None = None) -> None:
    """Open a terminal window inside `name`.

    Windows Terminal if it is there, which it is on Windows 11, because it
    gives the window a title and tabs; otherwise the console `wsl.exe` opens
    on its own. Either way the shell is a login shell, so the distribution's
    profile is read and `env` — the proxy variables, when they are configured —
    is exported before the user gets the prompt.
    """
    wsl._require_windows()
    if not wsl.registered(name):
        raise WslError(f"{name}: not registered")

    inner = ["wsl.exe", "-d", name, "--cd", directory]
    if env:
        # shlex, not repr: a proxy password is allowed to contain a quote.
        exports = "".join(f"export {key}={shlex.quote(value)}; " for key, value in env.items())
        inner += ["--", "bash", "-lc", f"{exports}exec bash -l"]

    if shutil.which("wt.exe"):
        detached(["wt.exe", "new-tab", "--title", f"WSL: {name}", *inner])
    else:
        # `start` needs a window title argument before the command, or it takes
        # the first quoted argument for one and opens an empty console.
        detached(["cmd.exe", "/c", "start", f"WSL: {name}", *inner])


def vscode(name: str, directory: str = "~") -> None:
    """Open `directory` of `name` in VS Code, running inside the distribution."""
    wsl._require_windows()
    if not wsl.registered(name):
        raise WslError(f"{name}: not registered")
    # `code` on PATH is a .cmd shim, which CreateProcess will not start on its
    # own — hence cmd /c, with the arguments still passed as separate argv
    # entries so nothing is re-parsed.
    detached(["cmd.exe", "/c", "code", "--remote", f"wsl+{name}", directory])


def vscode_installed() -> bool:
    """Is the `code` command on PATH?"""
    if shutil.which("code") or shutil.which("code.cmd"):
        return True
    try:
        return subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["cmd.exe", "/c", "code", "--version"],
            capture_output=True,
            check=False,
        ).returncode == 0
    except OSError:
        return False
