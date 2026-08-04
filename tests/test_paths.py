from __future__ import annotations

import sys
from pathlib import Path

import pytest

from wslx.paths import config_dir, instance_dir, state_dir


def test_config_dir_is_named_wslx() -> None:
    assert config_dir().name == "wslx"


@pytest.mark.skipif(sys.platform == "win32", reason="XDG is a unix convention")
def test_config_dir_honours_xdg_config_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg-wslx-test")
    assert config_dir() == Path("/tmp/xdg-wslx-test/wslx")


@pytest.mark.skipif(sys.platform != "win32", reason="APPDATA is windows-only")
def test_config_dir_honours_appdata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPDATA", r"C:\Users\box\AppData\Roaming")
    assert config_dir() == Path(r"C:\Users\box\AppData\Roaming\wslx")


def test_state_dir_creates_the_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    created = state_dir("cache")
    assert created.is_dir()
    assert created == tmp_path / "wslx" / "cache"


def test_instance_dir_is_under_the_config_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    assert instance_dir("alfa") == config_dir() / "alfa"
