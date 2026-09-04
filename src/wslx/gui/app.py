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

from .. import __version__, config
from ..run import windows
from . import theme as theming
from .common import Worker, scale_fonts
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
        # Monospaced so the progress transcript lines up; the size is set by
        # `_zoom` a moment later, from the scale the user last chose.
        self.log.SetFont(wx.Font(wx.FontInfo(9).Family(wx.FONTFAMILY_TELETYPE)))
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

        # Whatever text size and colours this user needed last time, they
        # still need.
        settings = config.load()
        self.scale = settings.font_scale
        self.theme = settings.theme
        if self.scale != 1.0:
            self._zoom(self.scale)
        if self.theme != "system":
            theming.apply(self, self.theme)
        if item := self.theme_items.get(self.theme):
            item.Check(True)

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

        view = wx.Menu()
        # Ctrl+= as well as Ctrl+Shift+=, because "zoom in" is Ctrl and the
        # plus key, and on most layouts that key is unshifted `=`. Accepting
        # only the shifted spelling is why zoom shortcuts so often "do
        # nothing" for the person trying them.
        bigger = view.Append(wx.ID_ANY, "&Bigger text\tCtrl++")
        bigger_alt = view.Append(wx.ID_ANY, "Bigger text\tCtrl+=")
        smaller = view.Append(wx.ID_ANY, "&Smaller text\tCtrl+-")
        view.AppendSeparator()
        normal = view.Append(wx.ID_ANY, "&Normal text size\tCtrl+0")

        self.Bind(wx.EVT_MENU, lambda event: self.zoom_by(config.FONT_SCALE_STEP), bigger)
        self.Bind(wx.EVT_MENU, lambda event: self.zoom_by(config.FONT_SCALE_STEP), bigger_alt)
        self.Bind(wx.EVT_MENU, lambda event: self.zoom_by(1 / config.FONT_SCALE_STEP), smaller)
        self.Bind(wx.EVT_MENU, lambda event: self.zoom_to(1.0), normal)

        # Radio items, because these are four answers to one question and the
        # menu should show which one is currently true.
        view.AppendSeparator()
        self.theme_items = {}
        for name, label in (
            ("system", "Follow the s&ystem"),
            ("white", "&White"),
            ("gray", "G&ray"),
            ("dark", "&Dark"),
        ):
            item = view.AppendRadioItem(wx.ID_ANY, label)
            self.theme_items[name] = item
            self.Bind(wx.EVT_MENU, lambda event, chosen=name: self.set_theme(chosen), item)
        bar.Append(view, "&View")
        return bar

    # --- looks ---------------------------------------------------------------

    def set_theme(self, name: str) -> None:
        """Repaint the window, and remember the choice."""
        name = config.clean_theme(name)
        self.theme = name
        theming.apply(self, name)
        config.update(theme=name)
        if item := self.theme_items.get(name):
            item.Check(True)
        # Windows draws the title bar, the menu bar and the scrollbars itself,
        # and only agrees to draw them dark if asked before the first window
        # exists — so say so rather than leaving a half-dark window looking
        # broken.
        pending = " — the title bar follows at the next launch" if windows() else ""
        self.SetStatusText(f"Theme: {name}{pending}")

    # --- text size ----------------------------------------------------------

    def zoom_by(self, factor: float) -> None:
        """Step the text size, clamped so it cannot be zoomed into uselessness."""
        self.zoom_to(self.scale * factor)

    def zoom_to(self, scale: float) -> None:
        scale = config.clamp_scale(scale)
        if scale == self.scale:
            return
        self.scale = scale
        self._zoom(scale)
        # Written straight away rather than on exit: a window that is closed by
        # the machine going to sleep should still open at the size you set.
        config.update(font_scale=scale)
        self.SetStatusText(f"Text size {round(scale * 100)}%")

    def _zoom(self, scale: float) -> None:
        scale_fonts(self, scale)
        # A ListCtrl sizes its columns for the font it had when they were made,
        # so the text grows and the columns do not. Re-fitting keeps the
        # heading readable at every size.
        for panel in self.tabs.values():
            table = getattr(panel, "table", None)
            if table is None:
                continue
            for column in range(table.GetColumnCount()):
                table.SetColumnWidth(column, wx.LIST_AUTOSIZE_USEHEADER)

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
    # Before the first window: Windows only offers dark frames if asked this
    # early, which is why the saved theme is read here and not by the frame.
    theming.enable_dark_titlebar(app, config.load().theme)
    frame = MainFrame()
    frame.Show()
    if not windows():
        frame.write("This is not Windows: nothing here can run. Layout preview only.")
    app.MainLoop()
