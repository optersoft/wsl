r"""The two configuration files, and which side of the wall each one is on.

`/etc/wsl.conf` lives **inside** a distribution and configures that one
machine: which user a session opens as, its hostname, whether Windows drives
are mounted and where. wslx already writes it once, through cloud-init, when a
machine is created; this module is how it is read and changed afterwards.

`%USERPROFILE%\.wslconfig` lives **on Windows** and configures the virtual
machine every distribution shares: how much memory and how many processors
they get between them, and which networking mode they are on. There is one of
these for the whole computer, and changing it takes effect at the next
`wsl --shutdown`, not immediately — the running VM keeps the settings it
booted with.

Both are ini files, so both are read with `configparser` rather than a
hand-rolled parser: it already handles the comments, the blank lines and the
`key = value` spacing that people leave behind when they edit these by hand.
"""

from __future__ import annotations

import configparser
import io
from pathlib import Path

from . import report, wsl
from .wsl import WslError

#: Where Windows keeps the shared virtual machine's configuration.
WSLCONFIG = Path.home() / ".wslconfig"


def parse(text: str) -> configparser.ConfigParser:
    """Parse ini text, keeping keys exactly as written.

    Both files are case-sensitive in a way configparser is not by default:
    `networkingMode` is not `networkingmode`, and WSL ignores the second.
    """
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # type: ignore[method-assign]
    parser.read_string(text or "")
    return parser


def render(parser: configparser.ConfigParser) -> str:
    buffer = io.StringIO()
    parser.write(buffer)
    return buffer.getvalue()


def get(parser: configparser.ConfigParser, section: str, key: str, default: str = "") -> str:
    return parser.get(section, key, fallback=default)


def put(parser: configparser.ConfigParser, section: str, key: str, value: str | None) -> None:
    """Set a key, or remove it when `value` is None.

    Removing matters more than it sounds: WSL treats a key that is present but
    empty differently from one that is absent, and the only way to go back to
    the default is for the key not to be there.
    """
    if value is None:
        if parser.has_section(section):
            parser.remove_option(section, key)
        return
    if not parser.has_section(section):
        parser.add_section(section)
    parser.set(section, key, value)


# --- /etc/wsl.conf, inside a distribution ------------------------------------


def read_conf(name: str) -> configparser.ConfigParser:
    """Read `/etc/wsl.conf` from `name`.

    A distribution that has never been configured has no such file, and `cat`
    says so on stderr; an empty parser is the right answer, not an error.
    """
    wsl._require_windows()
    return parse(wsl.capture("-d", name, "--user", "root", "--exec", "cat", "/etc/wsl.conf"))


def write_conf(name: str, parser: configparser.ConfigParser) -> None:
    """Replace `/etc/wsl.conf` in `name`, keeping a copy of what was there.

    The file goes in through a heredoc, and the whole script is one argument of
    an argv list — so nothing here is parsed by a Windows shell, whatever the
    distribution is called.

    The change lands at the distribution's next start; a running one keeps
    what it booted with, which is why this stops it.
    """
    wsl._require_windows()
    if not wsl.registered(name):
        raise WslError(f"{name}: not registered")

    script = (
        "cp /etc/wsl.conf /etc/wsl.conf.bak 2>/dev/null || true\n"
        "cat > /etc/wsl.conf <<'WSLX_EOF'\n"
        f"{render(parser)}"
        "WSLX_EOF\n"
    )
    result = wsl.execute("-d", name, "--user", "root", "--exec", "sh", "-c", script)
    if not result.ok:
        raise WslError(f"{name}: could not write /etc/wsl.conf — {result.message}")

    if wsl.running(name):
        wsl.stop(name)
    report.say(f"{name}: /etc/wsl.conf written (the old one is at /etc/wsl.conf.bak)")


# --- ~/.wslconfig, on Windows ------------------------------------------------


def read_wslconfig() -> configparser.ConfigParser:
    """Read `%USERPROFILE%\\.wslconfig`, empty if there is none."""
    text = WSLCONFIG.read_text(encoding="utf-8") if WSLCONFIG.is_file() else ""
    return parse(text)


def write_wslconfig(parser: configparser.ConfigParser) -> None:
    """Write `%USERPROFILE%\\.wslconfig`.

    Says out loud that it does nothing until the virtual machine restarts,
    because the alternative is someone setting a memory limit, watching Task
    Manager not change, and setting it again.
    """
    WSLCONFIG.write_text(render(parser), encoding="utf-8")
    report.say(f"{WSLCONFIG} written — run `wslx shutdown` for it to take effect")


def networking_mode() -> str:
    """`nat` (the default) or `mirrored`.

    Worth asking before making a port forward: in mirrored mode the
    distribution answers on the host's own addresses and a forward is not only
    unnecessary, it forwards to an address that is not the machine's.
    """
    return get(read_wslconfig(), "wsl2", "networkingMode", "nat").lower()
