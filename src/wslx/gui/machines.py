"""The machines tab: what you have, and what you can do to it.

This is the window's reason to exist. The CLI is better for the things you do
to a machine you already know the name of; a list is better for the two
questions a command line answers badly — *what have I got*, and *what is it
costing me*. So the columns are the ones that change what you do next: whether
it is running, how big its disk has grown on Windows, how full it is inside,
and the address it is reachable at.

The row is refreshed from three sources at different costs, which is why the
last two columns are empty for a stopped machine: asking a stopped machine how
full it is would boot it, and a list that starts every machine it shows would
be an unpleasant surprise.
"""

from __future__ import annotations

from pathlib import Path

import wx

from .. import backup, config, info, integrations, wsl, wslconf
from .common import Table, ask, confirm, toolbar

COLUMNS = (
    ("Name", 150),
    ("State", 80),
    ("WSL", 50),
    ("Managed", 75),
    ("Disk", 90),
    ("Used inside", 120),
    ("Address", 120),
)


class MachinesPanel(wx.Panel):
    def __init__(self, parent: wx.Window, frame) -> None:  # noqa: ANN001 - the frame owns the worker
        super().__init__(parent)
        self.frame = frame
        self.table = Table(self, COLUMNS)
        self.table.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_terminal)
        self.table.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self.on_menu)

        buttons = toolbar(
            self,
            [
                ("New", self.on_new),
                ("Start", self.on_start),
                ("Stop", self.on_stop),
                ("Terminal", self.on_terminal),
                ("VS Code", self.on_code),
                ("Files", self.on_files),
                ("-", None),
                ("Delete", self.on_delete),
                ("Refresh", lambda event: self.refresh()),
            ],
        )
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(buttons, 0, wx.ALL | wx.EXPAND, 6)
        sizer.Add(self.table, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        self.SetSizer(sizer)

    # --- data ---------------------------------------------------------------

    def refresh(self) -> None:
        self.frame.worker.submit(
            "Reading distributions", self._collect, done=self._show, quiet=True
        )

    @staticmethod
    def _collect() -> list[info.Info]:
        return [
            info.info(distribution.name, inside=True)
            for distribution in wsl.list_distributions()
        ]

    def _show(self, rows: list[info.Info]) -> None:
        self.table.fill(rows, self._cells)
        self.frame.machines = [row.name for row in rows]

    @staticmethod
    def _cells(row: info.Info) -> list[str]:
        # Percentage first, and only the total spelled out: a column wide
        # enough for "2.80 GB of 60.00 GB (5%)" is a column stealing space
        # from the name, and the number that decides anything is the percent.
        usage = f"{row.usage.percent}% of {info.human(row.usage.total)}" if row.usage else ""
        return [
            f"{row.name} *" if row.default else row.name,
            "Running" if row.running else "Stopped",
            str(row.version),
            "yes" if row.managed else "no",
            info.human(row.vhdx_size) if row.vhdx_size else "",
            usage,
            row.address or "",
        ]

    @property
    def selected(self) -> str | None:
        row = self.table.selection
        return row.name if row else None

    def _need(self) -> str | None:
        name = self.selected
        if name is None:
            wx.MessageBox("Select a machine first.", "wslx", wx.OK | wx.ICON_INFORMATION, self)
        return name

    def _do(self, label: str, work, *args) -> None:  # noqa: ANN001 - any core callable
        self.frame.worker.submit(label, lambda: work(*args), done=lambda _: self.refresh())

    # --- the toolbar --------------------------------------------------------

    def on_new(self, event: wx.Event) -> None:
        name = ask(self, "Name for the new machine:", "New machine")
        if name:
            self._do(f"Creating {name}", wsl.create, name)

    def on_start(self, event: wx.Event) -> None:
        if name := self._need():
            self._do(f"Starting {name}", wsl.start, name)

    def on_stop(self, event: wx.Event) -> None:
        if name := self._need():
            self._do(f"Stopping {name}", wsl.stop, name)

    def on_terminal(self, event: wx.Event) -> None:
        """Open a shell. Not through the worker: this one opens a window.

        The other operations block until `wsl.exe` finishes, which is why they
        run on a thread. A terminal is the opposite — the point is that it
        outlives the call — so it is started detached and returns at once.
        """
        if name := self._need():
            settings = config.load()
            directory = settings.directories.get(name, "~")
            integrations.terminal(name, directory, settings.proxy.environment())

    def on_code(self, event: wx.Event) -> None:
        if name := self._need():
            integrations.vscode(name, config.directory(name))

    def on_files(self, event: wx.Event) -> None:
        if name := self._need():
            integrations.explorer(name)

    def on_delete(self, event: wx.Event) -> None:
        name = self._need()
        if not name:
            return
        if confirm(
            self,
            f"Delete {name}?\n\nThe disk and everything in it goes. "
            "There is no recycle bin for this.",
            "Delete machine",
        ):
            self._do(f"Deleting {name}", wsl.delete, name)

    # --- the rest, on the right button --------------------------------------

    def on_menu(self, event: wx.Event) -> None:
        name = self.selected
        if not name:
            return
        menu = wx.Menu()
        entries = [
            ("Details ...", self.on_details),
            ("Set as default", self.on_default),
            ("Clone ...", self.on_clone),
            (None, None),
            ("Export to a file ...", self.on_export),
            ("Restore from a file ...", self.on_restore),
            (None, None),
            ("Compact the disk", self.on_compact),
            ("Move the disk ...", self.on_move),
            ("Make the disk sparse", self.on_sparse),
            (None, None),
            ("Edit /etc/wsl.conf ...", self.on_conf),
        ]
        for label, handler in entries:
            if label is None:
                menu.AppendSeparator()
                continue
            item = menu.Append(wx.ID_ANY, label)
            self.Bind(wx.EVT_MENU, handler, item)
        self.PopupMenu(menu)
        menu.Destroy()

    def on_details(self, event: wx.Event) -> None:
        """The rest of what `wslx info` prints.

        The columns hold what you compare between machines; this holds what you
        only want about one of them — where its disk is, what release it turned
        out to be, which uid a session opens as.
        """
        name = self.selected
        if not name:
            return
        self.frame.worker.submit(
            f"Reading {name}",
            lambda: info.info(name, inside=True),
            done=self._show_details,
        )

    def _show_details(self, detail: info.Info) -> None:
        rows = [
            ("Name", detail.name + (" (default)" if detail.default else "")),
            ("State", "Running" if detail.running else "Stopped"),
            ("WSL version", str(detail.version)),
            ("Managed by wslx", "yes" if detail.managed else "no"),
            ("From the Store", "yes" if detail.from_store else "no"),
            ("Release", detail.release or "(only a running machine can say)"),
            ("Address", detail.address or "-"),
            ("Disk", str(detail.vhdx) if detail.vhdx else "-"),
            (
                "Disk size",
                f"{info.human(detail.vhdx_size)}"
                + ("" if detail.sparse else "  (not sparse: it only ever grows)"),
            ),
            (
                "Used inside",
                f"{info.human(detail.usage.used)} of {info.human(detail.usage.total)} "
                f"({detail.usage.percent}%)"
                if detail.usage
                else "-",
            ),
            ("Default user id", str(detail.default_uid)),
        ]
        text = "\n".join(f"{label:<18}{value}" for label, value in rows)
        with wx.MessageDialog(self, text, detail.name, wx.OK | wx.ICON_INFORMATION) as dialog:
            dialog.ShowModal()

    def on_default(self, event: wx.Event) -> None:
        if name := self.selected:
            self._do(f"Making {name} the default", backup.set_default, name)

    def on_clone(self, event: wx.Event) -> None:
        source = self.selected
        if not source:
            return
        name = ask(self, f"Name for the copy of {source}:", "Clone machine", f"{source}-copy")
        if name:
            self._do(f"Cloning {source} to {name}", backup.clone, source, name)

    def on_export(self, event: wx.Event) -> None:
        name = self.selected
        if not name:
            return
        with wx.FileDialog(
            self,
            f"Back {name} up to",
            defaultFile=f"{name}.tar",
            wildcard="Tarball (*.tar)|*.tar|Disk image (*.vhdx)|*.vhdx",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            path = Path(dialog.GetPath())
        self._do(f"Exporting {name}", backup.export, name, path)

    def on_restore(self, event: wx.Event) -> None:
        with wx.FileDialog(
            self,
            "Restore from",
            wildcard="Backups (*.tar;*.tar.gz;*.vhdx)|*.tar;*.tar.gz;*.vhdx",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            path = Path(dialog.GetPath())
        name = ask(self, "Name for the restored machine:", "Restore", path.stem)
        if name:
            self._do(f"Restoring {name}", backup.restore, name, path)

    def on_compact(self, event: wx.Event) -> None:
        name = self.selected
        if not name:
            return
        if confirm(
            self,
            f"Compact {name}'s disk?\n\nThe machine is stopped first, and Windows "
            "asks for administrator permission.",
            "Compact disk",
        ):
            self._do(f"Compacting {name}", backup.compact, name)

    def on_move(self, event: wx.Event) -> None:
        name = self.selected
        if not name:
            return
        with wx.DirDialog(self, f"Move {name}'s disk to") as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            target = Path(dialog.GetPath())
        self._do(f"Moving {name}", backup.move, name, target)

    def on_sparse(self, event: wx.Event) -> None:
        if name := self.selected:
            self._do(f"Making {name}'s disk sparse", backup.set_sparse, name, True)

    def on_conf(self, event: wx.Event) -> None:
        """Edit /etc/wsl.conf as text.

        A form with a field per setting was the other option and it was worse:
        wsl.conf has keys this tool does not know about, and a form quietly
        deletes what it cannot show.
        """
        name = self.selected
        if not name:
            return
        self.frame.worker.submit(
            f"Reading {name}'s wsl.conf",
            lambda: wslconf.render(wslconf.read_conf(name)),
            done=lambda text: self._edit_conf(name, text),
        )

    def _edit_conf(self, name: str, text: str) -> None:
        style = wx.TE_MULTILINE | wx.OK | wx.CANCEL
        with wx.TextEntryDialog(
            self, f"/etc/wsl.conf in {name}", "wsl.conf", text, style=style
        ) as dialog:
            dialog.SetSize((520, 420))
            if dialog.ShowModal() != wx.ID_OK:
                return
            edited = dialog.GetValue()
        self._do(f"Writing {name}'s wsl.conf", wslconf.write_conf, name, wslconf.parse(edited))
