"""How the window looks: the system's answer, or one of three of our own.

`system` is the default, and it is read from the OS rather than hard-coded, so
the window matches whatever this computer's theme currently is. It is a real
palette like the others because the tempting alternative — unsetting every
colour with `wx.NullColour` — asserts *invalid colour* on macOS the moment you
switch back to it, which turned "return to the system look" into a crash.

The other three exist because "follow the system" is not always the answer
people want. A shared classroom machine is often on a light theme that a
projector washes out; a laptop at night is often on a dark one that a
photosensitive user cannot read. So: `white`, `gray` and `dark`, chosen and
remembered per user.

Applying a palette walks the widget tree, for the same reason
:func:`~wslx.gui.common.scale_fonts` does — a colour set on a parent does not
reach children that already exist.
"""

from __future__ import annotations

from dataclasses import dataclass

import wx


@dataclass(frozen=True)
class Palette:
    """The four colours the window actually distinguishes."""

    #: Panels, toolbars, the notebook.
    background: str
    #: Every label and every button caption.
    foreground: str
    #: The tables and the log, which sit inside a panel and want to be read as
    #: content rather than as chrome.
    surface: str
    #: Text on that surface.
    text: str


PALETTES = {
    # Not pure white: a full-brightness field behind small text is the thing
    # people turn the brightness down to escape.
    "white": Palette(background="#f3f3f3", foreground="#1a1a1a", surface="#ffffff", text="#1a1a1a"),
    # The middle option: dim enough for a dark room, light enough that a
    # projector still shows the table's grid lines.
    "gray": Palette(background="#4a4d50", foreground="#f0f0f0", surface="#5a5e62", text="#ffffff"),
    "dark": Palette(background="#1f1f1f", foreground="#e6e6e6", surface="#252526", text="#e6e6e6"),
}


def system_palette() -> Palette:
    """The colours this computer is using right now.

    Read at the moment it is applied, not cached: a machine that switched to
    dark mode since the window opened gets the new colours the next time the
    user picks "follow the system", and in any case at the next launch.
    """

    def colour(index: int) -> str:
        return wx.SystemSettings.GetColour(index).GetAsString(wx.C2S_HTML_SYNTAX)

    return Palette(
        background=colour(wx.SYS_COLOUR_BTNFACE),
        foreground=colour(wx.SYS_COLOUR_BTNTEXT),
        surface=colour(wx.SYS_COLOUR_WINDOW),
        text=colour(wx.SYS_COLOUR_WINDOWTEXT),
    )


#: Controls the platform draws itself, which are left in the system's colours.
#:
#: A button, a tab and a dropdown are painted by Windows and by macOS with
#: their own themed renderers, and setting a foreground on them mostly does not
#: take — what you get is a light caption left on a light button, i.e. an
#: unreadable control, which is worse than one that does not match. So the
#: palette claims the surfaces it can actually repaint and leaves the chrome
#: alone; the result is a themed window with native buttons, which is what most
#: applications that offer a dark mode over native widgets end up with.
NATIVE = (wx.Button, wx.Choice, wx.CheckBox, wx.Notebook, wx.RadioButton)


def apply(window: wx.Window, name: str) -> None:
    """Paint `window` and everything under it in the palette called `name`."""
    palette = PALETTES.get(name) or system_palette()

    def paint(target: wx.Window) -> None:
        if isinstance(target, NATIVE):
            # Its children still get painted: a notebook's pages are ours.
            for child in target.GetChildren():
                paint(child)
            return
        if isinstance(target, wx.ListCtrl):
            # A list draws its own rows: the background is the control's, but
            # the row text follows SetTextColour and nothing else.
            target.SetBackgroundColour(palette.surface)
            target.SetTextColour(palette.text)
        elif isinstance(target, wx.TextCtrl):
            target.SetBackgroundColour(palette.surface)
            target.SetForegroundColour(palette.text)
        else:
            target.SetBackgroundColour(palette.background)
            target.SetForegroundColour(palette.foreground)
        for child in target.GetChildren():
            paint(child)

    paint(window)
    window.Refresh()


def enable_dark_titlebar(app: wx.App, name: str) -> None:
    """Ask Windows for dark window frames, when that is what was chosen.

    The palette above paints what wxPython draws; the title bar, the menu bar
    and the scrollbars are drawn by Windows, and a dark window inside a white
    frame looks like a bug rather than a choice. wxWidgets 3.3 can ask for the
    dark variant, but only before the first window exists — so this is called
    from `launch`, with the saved theme, and a theme changed during a session
    finishes arriving at the next launch.

    Guarded twice over: the call is Windows-only and new, so a wxPython without
    it must not stop the window from opening.
    """
    if name != "dark" or not hasattr(app, "MSWEnableDarkMode"):
        return
    try:
        app.MSWEnableDarkMode()
    except Exception:  # noqa: BLE001 - a title bar is never worth a crash
        pass
