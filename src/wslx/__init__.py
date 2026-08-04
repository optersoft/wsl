"""wslx — manage Ubuntu WSL virtual machines.

Python port of the `box-wsl` crate from https://gitlab.com/xtec/box, which was
itself a port of the PowerShell `Box/Wsl.ps1`.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("wslx")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0+dev"

__all__ = ["__version__"]
