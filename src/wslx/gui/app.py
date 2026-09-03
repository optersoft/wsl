"""The window.

Six tabs and a log. The log is the part worth arguing for: every operation
here ends up as one or more Windows commands, some of them slow and some of
them asking for administrator permission, and a GUI that shows only a spinner
leaves people guessing about what it did to their machine. So the same
progress lines the CLI prints are written into a pane at the bottom, and stay
there — the window is a front end to a command-line tool and does not pretend
otherwise.
"""

from __future__ import annotations

import wx

from .. import __version__
from ..run import windows
from .common import Worker
from .machines import MachinesPanel
from .system import DisksPanel, NetworkPanel, SettingsPanel, TasksPanel, UsbPanel, shutdown_wsl


class MainFrame(wx.Frame):
    def __init__(self) -> None:
        super().__init__(None, title=f"wslx {__version__}", size=(980, 660))
        self.machines: list[str] = []

        splitter = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE | wx.SP_3DSASH)
        self.notebook = wx.Notebook(splitter)
        self.log = wx.TextCtrl(
            splitter, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP | wx.BORDER_NONE
        )
        self.log.SetFont(
            wx.Font(wx.FontInfo(9).Family(wx.FONTFAMILY_TELETYPE))
        )
        splitter.SplitHorizontally(self.notebook, self.log, -140)
        splitter.SetMinimumPaneSize(80)

        self.CreateStatusBar()
        self.worker = Worker(self.write, self.SetStatusText)

        self.machines_panel = MachinesPanel(self.notebook, self)
        self.tabs = {
            "Machines": self.machines_panel,
            "Network": NetworkPanel(self.notebook, self),
            "USB": UsbPanel(self.notebook, self),
            "Tasks": TasksPanel(self.notebook, self),
            "Disks": DisksPanel(self.notebook, self),
            "Settings": SettingsPanel(self.notebook, self),
        }
        for label, panel in self.tabs.items():
            self.notebook.AddPage(panel, label)
        # A tab loads when it is opened, not at startup: the disks tab runs two
        # PowerShell queries and the USB tab shells out to usbipd, and paying
        # for all six before the window appears is what makes a tool feel slow.
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_page)

        self.SetMenuBar(self._menus())
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.refresh()

    def _menus(self) -> wx.MenuBar:
        bar = wx.MenuBar()

        machine = wx.Menu()
        new = machine.Append(wx.ID_NEW, "&New machine\tCtrl+N")
        refresh = machine.Append(wx.ID_REFRESH, "&Refresh\tF5")
        machine.AppendSeparator()
        stop_all = machine.Append(wx.ID_ANY, "Shut &down WSL")
        machine.AppendSeparator()
        quit_ = machine.Append(wx.ID_EXIT, "&Quit\tCtrl+Q")
        bar.Append(machine, "&Machine")

        self.Bind(wx.EVT_MENU, self.machines_panel.on_new, new)
        self.Bind(wx.EVT_MENU, lambda event: self.refresh(), refresh)
        self.Bind(wx.EVT_MENU, lambda event: shutdown_wsl(self), stop_all)
        self.Bind(wx.EVT_MENU, lambda event: self.Close(), quit_)
        return bar

    # --- the log ------------------------------------------------------------

    def write(self, message: str, newline: bool = True) -> None:
        """Append to the log, leaving a half-written line open when asked."""
        self.log.AppendText(message.rstrip("\n") + ("\n" if newline else ""))

    # --- refreshing ---------------------------------------------------------

    def refresh(self) -> None:
        """Reload the tab in front, and the machine list it depends on.

        The machine list is reloaded whichever tab is open, because three of
        the others ask "which machine?" and need names to offer.
        """
        self.machines_panel.refresh()
        panel = self.notebook.GetCurrentPage()
        if panel is not self.machines_panel and hasattr(panel, "refresh"):
            panel.refresh()

    def on_page(self, event: wx.Event) -> None:
        panel = self.notebook.GetPage(event.GetSelection())
        if hasattr(panel, "refresh"):
            panel.refresh()
        event.Skip()

    def on_close(self, event: wx.Event) -> None:
        self.Destroy()


def launch() -> None:
    """Open the window.

    Off Windows this still runs and still draws: the panels come up empty
    because nothing is registered, which is exactly what a machine with no WSL
    looks like. That is what makes the layout workable from the Mac this is
    written on — but every button will refuse, so it says so once.
    """
    app = wx.App()
    frame = MainFrame()
    frame.Show()
    if not windows():
        frame.write("This is not Windows: nothing here can run. Layout preview only.")
    app.MainLoop()
