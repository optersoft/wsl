"""`wslx` — Ubuntu WSL virtual machine manager."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from . import __version__, backup, config, integrations, network, scheduler, wsl, wslconf
from . import info as info_
from . import mount as mount_
from . import usb as usb_
from .wsl import WslError

app = typer.Typer(
    name="wslx",
    help="Manage Ubuntu WSL virtual machines.",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()
errors = Console(stderr=True)

SCHEDULE_HELP = ", ".join(scheduler.SCHEDULES)

NameArg = Annotated[str, typer.Argument(help="Distribution name.")]
NamesArg = Annotated[list[str], typer.Argument(help="Distribution names.")]


def _version(value: bool) -> None:
    if value:
        console.print(f"wslx {__version__}")
        raise typer.Exit


@app.callback()
def main_callback(
    version: Annotated[  # noqa: ARG001 - consumed by the eager callback
        bool,
        typer.Option("--version", callback=_version, is_eager=True, help="Show the version."),
    ] = False,
) -> None:
    pass


@app.command()
def create(names: NamesArg) -> None:
    """Create one or more WSL distributions."""
    for name in names:
        wsl.create(name)


@app.command()
def start(names: NamesArg) -> None:
    """Start one or more WSL distributions."""
    for name in names:
        wsl.start(name)


@app.command()
def stop(names: NamesArg) -> None:
    """Stop (terminate) one or more WSL distributions."""
    for name in names:
        wsl.stop(name)


@app.command()
def delete(names: NamesArg) -> None:
    """Delete one or more WSL distributions."""
    for name in names:
        wsl.delete(name)


@app.command(name="list")
def list_() -> None:
    """List WSL distributions."""
    distributions = wsl.list_distributions()
    if not distributions:
        console.print("No WSL distributions registered.")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Name")
    table.add_column("State")
    table.add_column("Version")
    table.add_column("Managed")

    for distribution in distributions:
        name = f"{distribution.name} *" if distribution.default else distribution.name
        managed = "yes" if wsl.managed(distribution.name) else "no"
        table.add_row(name, distribution.state, distribution.version, managed)

    console.print(table)
    console.print("[dim]* default distribution[/dim]")


@app.command()
def connect(
    name: NameArg,
    new: Annotated[
        bool,
        typer.Option("--new", "-n", help="Create the distribution first."),
    ] = False,
) -> None:
    """Open a shell in a WSL distribution."""
    wsl.connect(name, new)


@app.command()
def info(name: NameArg) -> None:
    """Show everything known about a distribution."""
    detail = info_.info(name, inside=True)

    table = Table(show_header=False, box=None)
    table.add_column(style="bold")
    table.add_column()
    table.add_row("Name", detail.name + (" (default)" if detail.default else ""))
    table.add_row("State", "Running" if detail.running else "Stopped")
    table.add_row("WSL version", str(detail.version))
    table.add_row("Managed by wslx", "yes" if detail.managed else "no")
    table.add_row("From the Store", "yes" if detail.from_store else "no")
    if detail.release:
        table.add_row("Release", detail.release)
    if detail.address:
        table.add_row("Address", detail.address)
    if detail.vhdx:
        table.add_row("Disk", str(detail.vhdx))
        size = info_.human(detail.vhdx_size)
        table.add_row("Disk size", size if detail.sparse else f"{size} (not sparse)")
    if detail.usage:
        used = info_.human(detail.usage.used)
        total = info_.human(detail.usage.total)
        table.add_row("Used inside", f"{used} of {total} ({detail.usage.percent}%)")
    table.add_row("Default user id", str(detail.default_uid))
    console.print(table)


@app.command()
def export(
    name: NameArg,
    file: Annotated[Path, typer.Argument(help="Where to write the backup.")],
    vhd: Annotated[bool, typer.Option("--vhd", help="Export a .vhdx, not a tarball.")] = False,
) -> None:
    """Back a distribution up to a file."""
    backup.export(name, file, vhd=vhd)


@app.command()
def restore(
    name: NameArg,
    file: Annotated[Path, typer.Argument(help="The backup to import.")],
) -> None:
    """Create a distribution from a backup — under any name you like."""
    backup.restore(name, file)


@app.command()
def clone(
    source: Annotated[str, typer.Argument(help="The distribution to copy.")],
    name: NameArg,
) -> None:
    """Copy a distribution to a new one."""
    backup.clone(source, name)


@app.command()
def move(
    name: NameArg,
    directory: Annotated[Path, typer.Argument(help="Where the disk should live.")],
) -> None:
    """Move a distribution's disk to another directory or drive."""
    backup.move(name, directory)


@app.command()
def compact(name: NameArg) -> None:
    """Shrink a distribution's disk to what is used inside it."""
    backup.compact(name)


@app.command()
def sparse(
    name: NameArg,
    off: Annotated[bool, typer.Option("--off", help="Make the disk non-sparse again.")] = False,
) -> None:
    """Let a distribution's disk give space back when files are deleted."""
    backup.set_sparse(name, not off)


@app.command()
def default(name: NameArg) -> None:
    """Make a distribution the default one."""
    backup.set_default(name)


@app.command()
def shutdown() -> None:
    """Stop every distribution and the virtual machine they share."""
    backup.shutdown()


@app.command(name="open")
def open_(
    name: NameArg,
    path: Annotated[str, typer.Argument(help="Path inside the distribution.")] = "",
) -> None:
    """Open a distribution's files in Explorer."""
    integrations.explorer(name, path)


@app.command()
def terminal(name: NameArg) -> None:
    """Open a terminal window inside a distribution."""
    integrations.terminal(name, config.directory(name), config.load().proxy.environment())


@app.command()
def code(name: NameArg) -> None:
    """Open a distribution in VS Code, over Remote-WSL."""
    integrations.vscode(name, config.directory(name))


@app.command()
def disks() -> None:
    """List the physical disks that can be mounted into WSL."""
    found = mount_.disks()
    if not found:
        console.print("No mountable physical disks.")
        return
    table = Table(show_header=True, header_style="bold")
    for column in ("Device", "Model", "Size", "Bus"):
        table.add_column(column)
    for disk in found:
        table.add_row(disk.device, disk.model, info_.human(disk.size), disk.interface)
    console.print(table)


@app.command()
def mount(
    target: Annotated[str, typer.Argument(help=r"A \\.\PHYSICALDRIVE<n> or a .vhdx file.")],
    partition: Annotated[int | None, typer.Option("--partition", "-p")] = None,
    filesystem: Annotated[str | None, typer.Option("--type", "-t")] = None,
    name: Annotated[str | None, typer.Option("--name", help="Mount point name.")] = None,
    bare: Annotated[bool, typer.Option("--bare", help="Attach the device, mount nothing.")] = False,
) -> None:
    """Mount a disk or a disk image into WSL."""
    vhd = target.lower().endswith((".vhd", ".vhdx"))
    where = mount_.mount(
        target, vhd=vhd, partition=partition, filesystem=filesystem, name=name, bare=bare
    )
    console.print(f"mounted at {where}")


@app.command()
def unmount(
    target: Annotated[str | None, typer.Argument(help="What to unmount (default: all).")] = None,
) -> None:
    """Unmount a disk from WSL."""
    mount_.unmount(target)


@app.command()
def vm(
    memory: Annotated[str | None, typer.Option("--memory", help="e.g. 8GB.")] = None,
    processors: Annotated[int | None, typer.Option("--processors")] = None,
    networking: Annotated[str | None, typer.Option("--networking", help="nat or mirrored.")] = None,
) -> None:
    """Show or change the settings every distribution shares (.wslconfig)."""
    parser = wslconf.read_wslconfig()
    if memory is None and processors is None and networking is None:
        console.print(wslconf.render(parser).strip() or "No .wslconfig — every default applies.")
        return
    wslconf.put(parser, "wsl2", "memory", memory)
    wslconf.put(parser, "wsl2", "processors", str(processors) if processors else None)
    wslconf.put(parser, "wsl2", "networkingMode", networking)
    wslconf.write_wslconfig(parser)


forward_app = typer.Typer(help="Publish a distribution's ports.", no_args_is_help=True)
usb_app = typer.Typer(help="Hand USB devices to a distribution.", no_args_is_help=True)
task_app = typer.Typer(help="Run commands in a distribution on a schedule.", no_args_is_help=True)
app.add_typer(forward_app, name="forward")
app.add_typer(usb_app, name="usb")
app.add_typer(task_app, name="task")


@forward_app.command("list")
def forward_list() -> None:
    """Every port forwarding rule on this machine."""
    rules = network.forwards()
    if not rules:
        console.print("No port forwarding rules.")
        return
    table = Table(show_header=True, header_style="bold")
    for column in ("Listen", "Port", "Connect", "Port"):
        table.add_column(column)
    for rule in rules:
        table.add_row(
            rule.listen_address, str(rule.listen_port), rule.connect_address, str(rule.connect_port)
        )
    console.print(table)


@forward_app.command("add")
def forward_add(
    name: NameArg,
    port: Annotated[int, typer.Argument(help="Port to publish on this machine.")],
    inside: Annotated[int | None, typer.Option("--inside", help="Port inside it.")] = None,
) -> None:
    """Publish a port of a running distribution."""
    rule = network.forward(name, port, inside)
    network.add(rule)
    settings = config.load()
    settings.forwards[str(rule.listen_port)] = {"distro": name, "connect_port": rule.connect_port}
    config.save(settings)


@forward_app.command("remove")
def forward_remove(
    port: Annotated[int, typer.Argument(help="The published port to withdraw.")],
) -> None:
    """Remove a port forwarding rule."""
    rules = {rule.listen_port: rule for rule in network.forwards()}
    rule = rules.get(port) or network.Forward(port, "0.0.0.0", port)
    network.remove(rule)
    settings = config.load()
    settings.forwards.pop(str(port), None)
    config.save(settings)


@forward_app.command("repair")
def forward_repair() -> None:
    """Re-point wslx's forwards at the distributions' current addresses.

    WSL gives a distribution a new address every time the virtual machine
    restarts, which is what breaks a forward that worked yesterday.
    """
    settings = config.load()
    if not settings.forwards:
        console.print("No forwards to repair.")
        return
    for listen_port, saved in settings.forwards.items():
        try:
            rule = network.forward(saved["distro"], listen_port, saved.get("connect_port"))
        except WslError as err:
            errors.print(f"[yellow]skipped[/yellow] {listen_port}: {err}")
            continue
        network.add(rule)


@usb_app.command("list")
def usb_list() -> None:
    """Every USB device usbipd knows about."""
    devices = usb_.devices()
    if not devices:
        console.print("No USB devices.")
        return
    table = Table(show_header=True, header_style="bold")
    for column in ("Bus id", "Device", "State"):
        table.add_column(column)
    for device in devices:
        table.add_row(device.busid, device.description, device.state)
    console.print(table)


@usb_app.command("attach")
def usb_attach(
    busid: Annotated[str, typer.Argument(help="Bus id from `wslx usb list`.")],
    name: Annotated[str | None, typer.Option("--distribution", "-d")] = None,
) -> None:
    """Give a USB device to a distribution."""
    usb_.attach(busid, name)


@usb_app.command("detach")
def usb_detach(busid: Annotated[str, typer.Argument(help="Bus id to take back.")]) -> None:
    """Take a USB device back from WSL."""
    usb_.detach(busid)


@task_app.command("list")
def task_list() -> None:
    """Every task wslx has scheduled."""
    tasks = scheduler.tasks()
    if not tasks:
        console.print("No scheduled tasks.")
        return
    table = Table(show_header=True, header_style="bold")
    for column in ("Name", "Schedule", "Next run", "Status"):
        table.add_column(column)
    for task in tasks:
        table.add_row(task.label, task.schedule, task.next_run, task.status)
    console.print(table)


@task_app.command("add")
def task_add(
    label: Annotated[str, typer.Argument(help="A name for the task.")],
    name: NameArg,
    command: Annotated[str, typer.Argument(help="The command to run inside it.")],
    schedule: Annotated[str, typer.Option("--schedule", help=SCHEDULE_HELP)] = "DAILY",
    at: Annotated[str | None, typer.Option("--at", help="Start time, HH:MM.")] = None,
    every: Annotated[str | None, typer.Option("--every", help="schtasks /MO modifier.")] = None,
) -> None:
    """Schedule a command to run inside a distribution."""
    scheduler.create(label, name, command, schedule=schedule, at=at, modifier=every)


@task_app.command("remove")
def task_remove(label: Annotated[str, typer.Argument(help="The task to delete.")]) -> None:
    """Delete a scheduled task."""
    scheduler.delete(label)


@task_app.command("run")
def task_run(label: Annotated[str, typer.Argument(help="The task to run now.")]) -> None:
    """Run a scheduled task immediately."""
    scheduler.run_now(label)


@app.command()
def gui() -> None:
    """Open the wslx window."""
    try:
        from .gui import launch  # noqa: PLC0415 - the GUI is an optional extra
    except ImportError as exc:  # pragma: no cover - depends on how wslx was installed
        raise WslError(
            'the GUI needs wxPython — install it with `uv tool install "wslx[gui]"` '
            '(or `pip install "wslx[gui]"`)'
        ) from exc
    launch()


def main() -> None:
    """Console-script entry point: turn `WslError` into a tidy exit."""
    try:
        app()
    except WslError as err:
        errors.print(f"[red]error:[/red] {err}")
        raise SystemExit(1) from err


if __name__ == "__main__":
    main()
