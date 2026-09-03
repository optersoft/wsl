"""Reaching a distribution's services from somewhere other than this machine.

`localhost` already works: WSL forwards it for you, which is why the nginx
container in the tutorial answers on the Windows browser with nothing
configured. What does not work is the *next* machine — a phone on the same
wifi, or the person sitting beside you — because the distribution's address is
on a virtual network that exists only inside this computer.

Two commands fix that, and both need administrator rights:

`netsh interface portproxy`  send a port on the Windows address to the
                             distribution's address.
`netsh advfirewall firewall` let the packets in at all, which is the half
                             everyone forgets and then spends an hour on.

wslx does them together, under one UAC prompt, and names its firewall rules so
it can find them again.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

from . import info, report, wsl
from .run import elevate_script, run
from .wsl import WslError

#: Prefix for the firewall rules wslx creates, so it only ever deletes its own.
RULE_PREFIX = "wslx"


@dataclass(frozen=True)
class Forward:
    """One port forwarding rule: listen here, connect there."""

    listen_port: int
    connect_address: str
    connect_port: int
    listen_address: str = "0.0.0.0"

    @property
    def rule(self) -> str:
        """The firewall rule name that belongs to this forward."""
        return f"{RULE_PREFIX} {self.listen_port}"

    def __str__(self) -> str:
        return (
            f"{self.listen_address}:{self.listen_port} -> "
            f"{self.connect_address}:{self.connect_port}"
        )


def port(value: int | str) -> int:
    """Validate a port number.

    Every value below reaches an elevated command line, so nothing gets there
    without being turned into an `int` first.
    """
    number = int(value)
    if not 1 <= number <= 65535:
        raise WslError(f"{value}: not a port number")
    return number


def address(value: str) -> str:
    """Validate an IPv4 address, for the same reason."""
    try:
        return str(ipaddress.IPv4Address(value.strip()))
    except ValueError as exc:
        raise WslError(f"{value}: not an IPv4 address") from exc


_ROW = re.compile(r"^(\S+)\s+(\d+)\s+(\S+)\s+(\d+)\s*$")


def parse_forwards(output: str) -> list[Forward]:
    """Read `netsh interface portproxy show v4tov4`.

    The table's headings are translated on a localised Windows and the column
    widths move, so rows are recognised by shape — address, port, address,
    port — and anything else is a heading, a rule, or a blank line.
    """
    forwards = []
    for line in output.splitlines():
        match = _ROW.match(line.strip())
        if not match:
            continue
        listen_address, listen_port, connect_address, connect_port = match.groups()
        try:
            listen_address = str(ipaddress.IPv4Address(listen_address))
            connect_address = str(ipaddress.IPv4Address(connect_address))
        except ValueError:
            continue
        forwards.append(
            Forward(
                listen_port=int(listen_port),
                connect_address=connect_address,
                connect_port=int(connect_port),
                listen_address=listen_address,
            )
        )
    return forwards


def forwards() -> list[Forward]:
    """Every port forwarding rule on this machine, wslx's or not.

    Reading needs no elevation; only changing does.
    """
    wsl._require_windows()
    return parse_forwards(run(["netsh", "interface", "portproxy", "show", "v4tov4"]).out)


def forward(name: str, listen_port: int | str, connect_port: int | str | None = None) -> Forward:
    """Build the forward that publishes a port of the distribution `name`.

    The distribution's address is asked for at the moment the rule is made,
    and that is the catch worth knowing: in the default NAT mode WSL hands out
    a new address every time the virtual machine restarts, so a rule made today
    points at nothing tomorrow. `wslx forward --repair` is the answer, not a
    cleverer rule.
    """
    listen = port(listen_port)
    connect = port(connect_port if connect_port is not None else listen_port)
    if not wsl.running(name):
        raise WslError(f"{name}: not running — start it before publishing a port")
    target = info.address(name)
    if not target:
        raise WslError(f"{name}: has no IPv4 address yet")
    return Forward(listen_port=listen, connect_address=target, connect_port=connect)


def add(rule: Forward, *, firewall: bool = True) -> None:
    """Add `rule`, replacing any rule already listening on that port.

    netsh refuses to add a second entry for a listen address and port, so the
    delete goes first — which also makes this the repair path: adding a forward
    that already exists points it at the distribution's current address.
    """
    wsl._require_windows()
    commands = [
        _portproxy_delete(rule),
        [
            "netsh",
            "interface",
            "portproxy",
            "add",
            "v4tov4",
            f"listenaddress={rule.listen_address}",
            f"listenport={rule.listen_port}",
            f"connectaddress={rule.connect_address}",
            f"connectport={rule.connect_port}",
        ],
    ]
    if firewall:
        commands += [_firewall_delete(rule), _firewall_add(rule)]

    report.say(f"forwarding {rule} (administrator permission required) ...")
    result = elevate_script(commands, name="wslx-forward")
    if not result.ok:
        raise WslError(f"could not add the forwarding rule — {result.message}")
    report.say(f"forwarding {rule}")


def remove(rule: Forward, *, firewall: bool = True) -> None:
    """Remove `rule` and the firewall rule wslx made with it."""
    wsl._require_windows()
    commands = [_portproxy_delete(rule)]
    if firewall:
        commands.append(_firewall_delete(rule))

    report.say(f"removing the forward on port {rule.listen_port} ...")
    result = elevate_script(commands, name="wslx-forward")
    if not result.ok:
        raise WslError(f"could not remove the forwarding rule — {result.message}")


def _portproxy_delete(rule: Forward) -> list[str]:
    return [
        "netsh",
        "interface",
        "portproxy",
        "delete",
        "v4tov4",
        f"listenaddress={rule.listen_address}",
        f"listenport={rule.listen_port}",
    ]


def _firewall_add(rule: Forward) -> list[str]:
    return [
        "netsh",
        "advfirewall",
        "firewall",
        "add",
        "rule",
        f"name={rule.rule}",
        "dir=in",
        "action=allow",
        "protocol=TCP",
        f"localport={rule.listen_port}",
    ]


def _firewall_delete(rule: Forward) -> list[str]:
    return ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule.rule}"]
