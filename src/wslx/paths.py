"""Where wslx keeps its state.

Port of `box_core::config_dir` / `box_dir`, renamed to `wslx`:

- windows: ``%APPDATA%\\wslx``
- unix:    ``$XDG_CONFIG_HOME/wslx`` (falling back to ``~/.config/wslx``)

Distributions imported by wslx live in ``<config_dir>/<name>/`` and cached
downloads in ``<config_dir>/cache/``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def config_dir() -> Path:
    """Per-user config/state directory for the whole tool."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        root = Path(appdata) if appdata else Path.home()
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        root = Path(xdg) if xdg else Path.home() / ".config"
    return root / "wslx"


def state_dir(*parts: str) -> Path:
    """Return ``<config_dir>/<parts...>``, creating it if it does not exist."""
    path = config_dir().joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def instance_dir(name: str) -> Path:
    """Directory holding a distribution's ``ext4.vhdx``."""
    return config_dir() / name


def cloud_init_file(name: str) -> Path:
    """WSL reads cloud-init from ``%USERPROFILE%\\.cloud-init\\<distro>.user-data``."""
    directory = Path.home() / ".cloud-init"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{name}.user-data"
