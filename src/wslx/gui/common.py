"""The two things every panel needs: a worker and a list.

**A worker**, because every operation here is a Windows program that takes
between 200 ms and four minutes, and wxPython draws nothing while its thread is
busy. So no panel calls the core directly: it hands the call to
:class:`Worker`, which runs it on one background thread, routes the progress
messages the core emits into the log pane, and comes back to the UI thread with
`wx.CallAfter`.

One thread, not a pool, and that is deliberate. Two `wsl.exe` operations on the
same distribution at the same time is how you get a half-exported tarball or an
import that races an unregister — and a queue makes the window's behaviour
obvious: the thing you clicked happens after the thing you clicked before it.

**A list**, because five of the six tabs are a table of things with a toolbar
above it, and writing `wx.ListCtrl` column setup five times is how the columns
end up different widths on each tab.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable, Sequence
from typing import Any

import wx

from .. import report
from ..run import RunError
from ..wsl import WslError


class Worker:
    """Runs core operations off the UI thread, one at a time."""

    def __init__(self, log: Callable[[str], None], status: Callable[[str], None]) -> None:
        self._log = log
        self._status = status
        #: label, the work, what to do with its result, and whether a failure
        #: is worth a dialog.
        Job = tuple[str, Callable[[], Any], Callable[[Any], None] | None, bool]
        self._jobs: queue.Queue[Job] = queue.Queue()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def submit(
        self,
        label: str,
        work: Callable[[], Any],
        *,
        done: Callable[[Any], None] | None = None,
        quiet: bool = False,
    ) -> None:
        """Queue `work`, calling `done` with its result on the UI thread.

        `quiet` is for the jobs nobody asked for — the refresh that runs when a
        tab is opened. Those fail for ordinary reasons (usbipd is not
        installed, nothing is registered yet) and a modal dialog in front of a
        window you have only just opened is the wrong way to say so. They go to
        the log; the ones the user clicked get a dialog.
        """
        self._jobs.put((label, work, done, quiet))
        wx.CallAfter(self._status, f"{label} ...")

    def _loop(self) -> None:
        while True:
            label, work, done, quiet = self._jobs.get()
            # The core reports progress through `report.say`; while this job
            # runs, that means a line in the log pane.
            with report.sink(lambda message, end: wx.CallAfter(self._log, message + end.strip())):
                try:
                    result = work()
                except (WslError, RunError) as error:
                    wx.CallAfter(self._failed, label, str(error), quiet)
                    continue
                except Exception as error:  # noqa: BLE001 - a GUI may not die on a bug
                    wx.CallAfter(self._failed, label, f"unexpected error: {error!r}", quiet)
                    continue
            wx.CallAfter(self._status, f"{label}: done")
            if done is not None:
                wx.CallAfter(done, result)

    def _failed(self, label: str, message: str, quiet: bool) -> None:
        self._log(f"error: {message}")
        self._status(f"{label}: failed")
        if not quiet:
            wx.MessageBox(message, label, wx.OK | wx.ICON_ERROR)


class Table(wx.ListCtrl):
    """A report-style list with named columns and a selection helper."""

    def __init__(self, parent: wx.Window, columns: Sequence[tuple[str, int]]) -> None:
        super().__init__(parent, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_NONE)
        for index, (heading, width) in enumerate(columns):
            self.InsertColumn(index, heading, width=width)
        self._rows: list[Any] = []

    def fill(self, rows: Sequence[Any], cells: Callable[[Any], Sequence[str]]) -> None:
        """Replace the contents, keeping the selection on the same row if it survived.

        Keeping it matters: the list refreshes after every operation, and a
        list that jumps back to the top each time makes "start, then connect"
        two clicks and a hunt.
        """
        selected = self.selection
        key = getattr(selected, "name", None) or getattr(selected, "busid", None)

        self.DeleteAllItems()
        self._rows = list(rows)
        for row, item in enumerate(self._rows):
            values = list(cells(item))
            self.InsertItem(row, values[0])
            for column, value in enumerate(values[1:], start=1):
                self.SetItem(row, column, value)

        for row, item in enumerate(self._rows):
            if key is not None and key in (
                getattr(item, "name", None),
                getattr(item, "busid", None),
            ):
                self.Select(row)
                self.Focus(row)
                break

    @property
    def selection(self) -> Any | None:
        """The object behind the selected row, not its text."""
        row = self.GetFirstSelected()
        return self._rows[row] if 0 <= row < len(self._rows) else None


def toolbar(parent: wx.Window, buttons: Sequence[tuple[str, Callable[[wx.Event], None]]]):
    """A row of buttons above a table."""
    sizer = wx.BoxSizer(wx.HORIZONTAL)
    for label, handler in buttons:
        if label == "-":
            sizer.AddStretchSpacer()
            continue
        button = wx.Button(parent, label=label)
        button.Bind(wx.EVT_BUTTON, handler)
        sizer.Add(button, 0, wx.RIGHT, 4)
    return sizer


def ask(parent: wx.Window, message: str, title: str, default: str = "") -> str | None:
    """A one-line text prompt. None when the user backs out."""
    with wx.TextEntryDialog(parent, message, title, default) as dialog:
        if dialog.ShowModal() != wx.ID_OK:
            return None
        value = dialog.GetValue().strip()
    return value or None


def confirm(parent: wx.Window, message: str, title: str) -> bool:
    """A yes/no the user has to mean — used before anything irreversible."""
    return (
        wx.MessageBox(message, title, wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, parent)
        == wx.YES
    )
