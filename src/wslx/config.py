"""What wslx remembers between runs.

Very little, on purpose. Two things cannot be derived from the machine and so
have to be written down: the **proxy** a terminal should be opened with, on the
networks where nothing reaches the internet without one, and the **port
forwards** wslx has made — because WSL hands a distribution a new address on
every restart, so a forward has to be re-pointed, and re-pointing it means
knowing it was ours.

Everything else the tool shows is asked for fresh, from `wsl.exe`, the registry
or the file system. Cached state that can go stale is worse than a command that
takes 200 ms.

The file is JSON at `%APPDATA%\\wslx\\settings.json`, and a corrupt or
hand-edited one is replaced rather than crashed on: it is a convenience, and
losing it costs a re-typed proxy.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from .paths import config_dir


@dataclass(frozen=True)
class Proxy:
    """An HTTP proxy to export into a terminal opened from wslx."""

    enabled: bool = False
    host: str = ""
    port: str = ""
    username: str = ""
    password: str = ""
    no_proxy: str = "localhost,127.0.0.1"

    @property
    def url(self) -> str:
        credentials = f"{self.username}:{self.password}@" if self.username else ""
        return f"http://{credentials}{self.host}:{self.port}"

    def environment(self) -> dict[str, str]:
        """The variables a shell needs, or nothing when the proxy is off.

        Both spellings, because half of the Linux world reads `HTTP_PROXY` and
        the other half `http_proxy`, and a student debugging `apt` behind a
        school proxy should not have to know which half `apt` is in.
        """
        if not (self.enabled and self.host and self.port):
            return {}
        variables = {}
        for name in ("HTTP_PROXY", "HTTPS_PROXY"):
            variables[name] = self.url
            variables[name.lower()] = self.url
        if self.no_proxy:
            variables["NO_PROXY"] = self.no_proxy
            variables["no_proxy"] = self.no_proxy
        return variables


#: How far the window's text may be scaled, and by how much per keypress.
FONT_SCALE_MIN = 0.7
FONT_SCALE_MAX = 2.5
FONT_SCALE_STEP = 1.1


@dataclass(frozen=True)
class Settings:
    """Everything wslx keeps."""

    proxy: Proxy = field(default_factory=Proxy)
    #: Per-distribution starting directory for terminals and the editor.
    directories: dict[str, str] = field(default_factory=dict)
    #: Port forwards wslx made: listen port -> {"distro": ..., "connect_port": ...}
    forwards: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: Text size in the window, as a multiple of the system's UI font. Kept
    #: here rather than recomputed per launch because someone who needed
    #: larger text last time still needs it this time.
    font_scale: float = 1.0


def path() -> Path:
    return config_dir() / "settings.json"


def load() -> Settings:
    """Read the settings, falling back to the defaults for anything missing."""
    try:
        raw = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Settings()
    if not isinstance(raw, dict):
        return Settings()
    return Settings(
        proxy=Proxy(**{**asdict(Proxy()), **(raw.get("proxy") or {})}),
        directories=dict(raw.get("directories") or {}),
        forwards=dict(raw.get("forwards") or {}),
        font_scale=clamp_scale(raw.get("font_scale", 1.0)),
    )


def clamp_scale(value: Any) -> float:
    """Keep a stored scale usable.

    A hand-edited or corrupt value must not produce a window whose text is
    invisible or a single letter per row, and neither must be a state a user
    can get stuck in.
    """
    try:
        scale = float(value)
    except (TypeError, ValueError):
        return 1.0
    return min(max(scale, FONT_SCALE_MIN), FONT_SCALE_MAX)


def save(settings: Settings) -> None:
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")


def update(**changes: Any) -> Settings:
    """Change some fields and write the result back."""
    settings = replace(load(), **changes)
    save(settings)
    return settings


def directory(name: str, default: str = "~") -> str:
    """Where terminals and the editor should open for `name`."""
    return load().directories.get(name, default)
