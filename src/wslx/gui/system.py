"""The tabs that are about the machine WSL runs on, not about one distribution.

Network, USB, scheduled tasks, disks and settings. Each is the same shape — a
table, a toolbar, and operations that go through the worker — because each is a
list of things Windows holds and wslx can add to or take away from.

Two of them tell the truth that the equivalent panels in most WSL front ends do
not. The network tab says which mode the shared VM is in, because a port
forward in mirrored mode is not just unnecessary, it points at an address the
distribution does not have. The USB tab says whether `usbipd-win` is installed
at all, rather than presenting an empty list that looks like "no devices".
"""

from __future__ import annotations

import wx

from .. import config, info, mount, network, scheduler, usb, wslconf
from .common import Table, ask, confirm, toolbar


class _Tab(wx.Panel):
    """A toolbar over a table, wired to the frame's worker."""

    columns: tuple[tuple[str, int], ...] = ()

    def __init__(self, parent: wx.Window, frame, buttons) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.frame = frame
        self.table = Table(self, self.columns)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(toolbar(self, buttons), 0, wx.ALL | wx.EXPAND, 6)
        self.banner = wx.StaticText(self, label="")
        sizer.Add(self.banner, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        sizer.Add(self.table, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        self.SetSizer(sizer)

    def load(self, label: str, work, cells) -> None:  # noqa: ANN001
        """Fill the table. Quiet: a refresh nobody asked for does not raise dialogs."""
        self.frame.worker.submit(
            label, work, done=lambda rows: self.table.fill(rows, cells), quiet=True
        )

    def machine(self) -> str | None:
        """Ask which distribution, defaulting to the one selected next door."""
        names = self.frame.machines
        if not names:
            wx.MessageBox("No distributions yet.", "wslx", wx.OK | wx.ICON_INFORMATION, self)
            return None
        with wx.SingleChoiceDialog(self, "Which machine?", "wslx", names) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return None
            return dialog.GetStringSelection()


class NetworkPanel(_Tab):
    columns = (("Listen on", 140), ("Port", 70), ("Connect to", 150), ("Port", 70))

    def __init__(self, parent: wx.Window, frame) -> None:  # noqa: ANN001
        super().__init__(
            parent,
            frame,
            [
                ("Publish a port", self.on_add),
                ("Remove", self.on_remove),
                ("Repair", self.on_repair),
                ("-", None),
                ("Refresh", lambda event: self.refresh()),
            ],
        )

    def refresh(self) -> None:
        self.load("Reading port forwards", network.forwards, self._cells)
        self.frame.worker.submit(
            "Reading .wslconfig", wslconf.networking_mode, done=self._mode, quiet=True
        )

    def _mode(self, mode: str) -> None:
        self.banner.SetLabel(
            "Networking mode: mirrored — the distributions already answer on this "
            "machine's addresses, so a forward is not needed."
            if mode == "mirrored"
            else "Networking mode: nat — WSL gives a new address on every restart, "
            "so a forward made yesterday may need Repair."
        )
        self.Layout()

    @staticmethod
    def _cells(rule: network.Forward) -> list[str]:
        return [
            rule.listen_address,
            str(rule.listen_port),
            rule.connect_address,
            str(rule.connect_port),
        ]

    def on_add(self, event: wx.Event) -> None:
        name = self.machine()
        if not name:
            return
        port = ask(self, f"Publish which port of {name}?", "Publish a port", "80")
        if not port:
            return

        def work() -> None:
            rule = network.forward(name, port)
            network.add(rule)
            settings = config.load()
            settings.forwards[str(rule.listen_port)] = {
                "distro": name,
                "connect_port": rule.connect_port,
            }
            config.save(settings)

        self.frame.worker.submit(f"Publishing port {port}", work, done=lambda _: self.refresh())

    def on_remove(self, event: wx.Event) -> None:
        rule = self.table.selection
        if rule is None:
            return
        self.frame.worker.submit(
            f"Removing the forward on {rule.listen_port}",
            lambda: network.remove(rule),
            done=lambda _: self.refresh(),
        )

    def on_repair(self, event: wx.Event) -> None:
        """Re-point every forward wslx made at the current address."""

        def work() -> None:
            for listen_port, saved in config.load().forwards.items():
                rule = network.forward(saved["distro"], listen_port, saved.get("connect_port"))
                network.add(rule)

        self.frame.worker.submit("Repairing forwards", work, done=lambda _: self.refresh())


class UsbPanel(_Tab):
    columns = (("Bus id", 80), ("Device", 320), ("State", 110))

    def __init__(self, parent: wx.Window, frame) -> None:  # noqa: ANN001
        super().__init__(
            parent,
            frame,
            [
                ("Attach", self.on_attach),
                ("Detach", self.on_detach),
                ("-", None),
                ("Refresh", lambda event: self.refresh()),
            ],
        )

    def refresh(self) -> None:
        if not usb.installed():
            self.banner.SetLabel(
                "usbipd-win is not installed — WSL cannot see USB devices without it. "
                "Install it with: winget install --exact dorssel.usbipd-win"
            )
            self.table.fill([], lambda device: [])
            self.Layout()
            return
        self.banner.SetLabel("Sharing a device asks for administrator permission, once per device.")
        self.load("Reading USB devices", usb.devices, self._cells)

    @staticmethod
    def _cells(device: usb.Device) -> list[str]:
        return [device.busid, device.description, device.state]

    def on_attach(self, event: wx.Event) -> None:
        device = self.table.selection
        if device is None:
            return
        name = self.machine()
        if not name:
            return
        self.frame.worker.submit(
            f"Attaching {device.busid}",
            lambda: usb.attach(device.busid, name),
            done=lambda _: self.refresh(),
        )

    def on_detach(self, event: wx.Event) -> None:
        device = self.table.selection
        if device is None:
            return
        self.frame.worker.submit(
            f"Detaching {device.busid}",
            lambda: usb.detach(device.busid),
            done=lambda _: self.refresh(),
        )


class TasksPanel(_Tab):
    columns = (("Task", 160), ("Schedule", 100), ("Next run", 170), ("Status", 90))

    def __init__(self, parent: wx.Window, frame) -> None:  # noqa: ANN001
        super().__init__(
            parent,
            frame,
            [
                ("Schedule a command", self.on_add),
                ("Run now", self.on_run),
                ("Delete", self.on_delete),
                ("-", None),
                ("Refresh", lambda event: self.refresh()),
            ],
        )

    def refresh(self) -> None:
        self.banner.SetLabel(
            "Windows starts these, so they run even though the distribution is stopped."
        )
        self.load("Reading scheduled tasks", scheduler.tasks, self._cells)

    @staticmethod
    def _cells(task: scheduler.Task) -> list[str]:
        return [task.label, task.schedule, task.next_run, task.status]

    def on_add(self, event: wx.Event) -> None:
        name = self.machine()
        if not name:
            return
        label = ask(self, "A name for the task:", "Schedule a command")
        if not label:
            return
        command = ask(self, f"Command to run inside {name}:", "Schedule a command", "apt update")
        if not command:
            return
        at = ask(self, "Start time (HH:MM), daily:", "Schedule a command", "09:00")
        self.frame.worker.submit(
            f"Scheduling {label}",
            lambda: scheduler.create(label, name, command, schedule="DAILY", at=at),
            done=lambda _: self.refresh(),
        )

    def on_run(self, event: wx.Event) -> None:
        task = self.table.selection
        if task is not None:
            self.frame.worker.submit(f"Running {task.label}", lambda: scheduler.run_now(task.label))

    def on_delete(self, event: wx.Event) -> None:
        task = self.table.selection
        if task is not None and confirm(self, f"Delete the task {task.label}?", "Delete task"):
            self.frame.worker.submit(
                f"Deleting {task.label}",
                lambda: scheduler.delete(task.label),
                done=lambda _: self.refresh(),
            )


class DisksPanel(_Tab):
    columns = (("Device", 190), ("Model", 260), ("Size", 100), ("Bus", 80))

    def __init__(self, parent: wx.Window, frame) -> None:  # noqa: ANN001
        super().__init__(
            parent,
            frame,
            [
                ("Mount", self.on_mount),
                ("Mount an image ...", self.on_mount_vhd),
                ("Unmount all", self.on_unmount),
                ("-", None),
                ("Refresh", lambda event: self.refresh()),
            ],
        )

    def refresh(self) -> None:
        self.banner.SetLabel(
            "The disk Windows boots from is not listed: mounting it would take it "
            "away from the running system. A mount is shared by every distribution."
        )
        self.load("Reading disks", mount.disks, self._cells)

    @staticmethod
    def _cells(disk: mount.Disk) -> list[str]:
        return [disk.device, disk.model, info.human(disk.size), disk.interface]

    def on_mount(self, event: wx.Event) -> None:
        disk = self.table.selection
        if disk is None:
            return
        partition = ask(self, "Which partition? (empty for the whole disk)", "Mount", "1")
        self.frame.worker.submit(
            f"Mounting {disk.device}",
            lambda: mount.mount(
                disk.device, partition=int(partition) if partition else None
            ),
            done=self._mounted,
        )

    def on_mount_vhd(self, event: wx.Event) -> None:
        with wx.FileDialog(
            self,
            "Mount a disk image",
            wildcard="Disk images (*.vhdx;*.vhd)|*.vhdx;*.vhd",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            path = dialog.GetPath()
        self.frame.worker.submit(
            f"Mounting {path}", lambda: mount.mount(path, vhd=True), done=self._mounted
        )

    def _mounted(self, where: str) -> None:
        wx.MessageBox(f"Mounted at {where}", "wslx", wx.OK | wx.ICON_INFORMATION, self)

    def on_unmount(self, event: wx.Event) -> None:
        self.frame.worker.submit("Unmounting", lambda: mount.unmount(None))


class SettingsPanel(wx.Panel):
    """The two files, side by side: the shared VM and the proxy.

    `.wslconfig` is Windows-side and applies to every distribution at once;
    the proxy is wslx's own, and only affects terminals wslx opens. Keeping
    them on one page is the only honest way to show that the memory limit is
    not per machine, which is what everybody assumes it is.
    """

    def __init__(self, parent: wx.Window, frame) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.frame = frame
        grid = wx.FlexGridSizer(cols=2, vgap=6, hgap=10)
        grid.AddGrowableCol(1, 1)

        def field(label: str, value: str = "") -> wx.TextCtrl:
            grid.Add(wx.StaticText(self, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            control = wx.TextCtrl(self, value=value)
            grid.Add(control, 1, wx.EXPAND)
            return control

        grid.Add(wx.StaticText(self, label="Shared virtual machine (.wslconfig)"), 0, wx.TOP, 4)
        grid.AddSpacer(0)
        self.memory = field("Memory", "")
        self.processors = field("Processors", "")
        grid.Add(wx.StaticText(self, label="Networking"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.networking = wx.Choice(self, choices=["nat", "mirrored"])
        grid.Add(self.networking, 0)

        grid.Add(wx.StaticText(self, label="Proxy for terminals wslx opens"), 0, wx.TOP, 12)
        grid.AddSpacer(0)
        self.proxy_enabled = wx.CheckBox(self, label="Use a proxy")
        grid.Add(self.proxy_enabled, 0)
        grid.AddSpacer(0)
        self.host = field("Host")
        self.port = field("Port")
        self.username = field("User")
        self.password = field("Password")
        self.password.SetWindowStyleFlag(self.password.GetWindowStyleFlag() | wx.TE_PASSWORD)
        self.no_proxy = field("No proxy for")

        save = wx.Button(self, label="Save")
        save.Bind(wx.EVT_BUTTON, self.on_save)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 12)
        sizer.Add(save, 0, wx.LEFT | wx.BOTTOM, 12)
        sizer.Add(
            wx.StaticText(
                self,
                label="Changes to the shared virtual machine take effect after "
                "Shut down WSL, not immediately.",
            ),
            0,
            wx.LEFT | wx.BOTTOM,
            12,
        )
        self.SetSizer(sizer)

    def refresh(self) -> None:
        parser = wslconf.read_wslconfig()
        self.memory.SetValue(wslconf.get(parser, "wsl2", "memory"))
        self.processors.SetValue(wslconf.get(parser, "wsl2", "processors"))
        mode = wslconf.get(parser, "wsl2", "networkingMode", "nat").lower()
        self.networking.SetSelection(1 if mode == "mirrored" else 0)

        proxy = config.load().proxy
        self.proxy_enabled.SetValue(proxy.enabled)
        self.host.SetValue(proxy.host)
        self.port.SetValue(proxy.port)
        self.username.SetValue(proxy.username)
        self.password.SetValue(proxy.password)
        self.no_proxy.SetValue(proxy.no_proxy)

    def on_save(self, event: wx.Event) -> None:
        parser = wslconf.read_wslconfig()
        wslconf.put(parser, "wsl2", "memory", self.memory.GetValue().strip() or None)
        wslconf.put(parser, "wsl2", "processors", self.processors.GetValue().strip() or None)
        wslconf.put(parser, "wsl2", "networkingMode", self.networking.GetStringSelection())
        proxy = config.Proxy(
            enabled=self.proxy_enabled.GetValue(),
            host=self.host.GetValue().strip(),
            port=self.port.GetValue().strip(),
            username=self.username.GetValue().strip(),
            password=self.password.GetValue(),
            no_proxy=self.no_proxy.GetValue().strip(),
        )
        self.frame.worker.submit(
            "Saving settings",
            lambda: (wslconf.write_wslconfig(parser), config.update(proxy=proxy)),
        )


def shutdown_wsl(frame) -> None:  # noqa: ANN001 - the frame owns the worker
    """Stop everything, which is also how a .wslconfig change takes effect."""
    from .. import backup  # noqa: PLC0415 - avoids a cycle at import time

    if confirm(
        frame,
        "Stop every distribution and the virtual machine they share?\n\n"
        "Anything running inside them is lost.",
        "Shut down WSL",
    ):
        frame.worker.submit("Shutting WSL down", backup.shutdown, done=lambda _: frame.refresh())


__all__ = [
    "DisksPanel",
    "NetworkPanel",
    "SettingsPanel",
    "TasksPanel",
    "UsbPanel",
    "shutdown_wsl",
]
