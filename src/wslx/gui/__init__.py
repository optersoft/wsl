"""wslx's window — an optional extra.

Installed with `wslx[gui]` and opened with `wslx gui`. Importing this package
imports wxPython, which is why nothing else in wslx imports it and why `wslx
gui` catches the ImportError and explains the extra.
"""

from __future__ import annotations

from .app import MainFrame, launch

__all__ = ["MainFrame", "launch"]
