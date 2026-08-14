"""Tests for the platform-independent parts of the WSL provider.

These run on any OS: the pure helpers must stay importable and correct even
where `wsl.exe` does not exist.
"""

from __future__ import annotations

import sys

import pytest

from wslx import wsl
from wslx.cloud_init import user_data
from wslx.wsl import Distribution, WslError, decode, parse_names, parse_verbose


def test_decode_utf16le() -> None:
    assert decode("Ubuntu\n".encode("utf-16-le")) == "Ubuntu\n"


def test_decode_utf8() -> None:
    assert decode(b"Ubuntu\n") == "Ubuntu\n"


def test_parse_names_drops_blank_and_carriage_returns() -> None:
    assert parse_names("Ubuntu\r\ndev\r\n\r\n") == ["Ubuntu", "dev"]


def test_parse_verbose_skips_the_header_and_marks_the_default() -> None:
    output = (
        "  NAME      STATE           VERSION\n"
        "* Ubuntu    Running         2\n"
        "  dev       Stopped         2\n"
    )
    assert parse_verbose(output) == [
        Distribution("Ubuntu", "Running", "2", default=True),
        Distribution("dev", "Stopped", "2", default=False),
    ]


def test_parse_verbose_ignores_short_rows() -> None:
    assert parse_verbose("NAME STATE VERSION\n  broken\n") == []


def test_parse_verbose_ignores_the_no_distributions_message() -> None:
    """A machine with no distributions gets prose, not a table.

    Captured verbatim from a Spanish Windows 10 22H2 guest, where `wsl --list
    --verbose` exits -1 and prints this. `_capture` drops the exit code, so the
    parser is the only thing standing between that prose and a bogus row —
    "Para instalar las" used to be listed as a distribution.
    """
    output = (
        "El subsistema de Windows para Linux no tiene distribuciones instaladas.\r\n"
        "\r\n"
        "Para instalar las distribuciones, se puede visitar Microsoft Store:\r\n"
        "\r\n"
        "https://aka.ms/wslstore\r\n"
    )
    assert parse_verbose(output) == []


def test_parse_verbose_ignores_the_english_no_distributions_message() -> None:
    output = (
        "Windows Subsystem for Linux has no installed distributions.\r\n"
        "\r\n"
        "Use 'wsl.exe --list --online' to list available distributions\r\n"
        "and 'wsl.exe --install <Distro>' to install.\r\n"
    )
    assert parse_verbose(output) == []


def test_start_boots_as_root_before_pinning_the_default_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The order is load-bearing in both directions.

    Pinning DefaultUid to 1000 first makes WSL boot with a default user that
    cloud-init has not created yet; the systemd user session then fails and
    cloud-init finishes degraded, leaving the distribution unseeded (observed
    on a windows-2025 runner). Booting explicitly as root avoids depending on
    whatever DefaultUid happens to hold from a previous run.
    """
    calls: list[str] = []
    monkeypatch.setattr(wsl, "_require_windows", lambda: None)
    monkeypatch.setattr(wsl, "running", lambda name: False)
    monkeypatch.setattr(wsl, "registered", lambda name: True)
    monkeypatch.setattr(wsl, "set_default_uid", lambda name, uid: calls.append(f"uid={uid}"))
    monkeypatch.setattr(wsl, "_call", lambda *args, error: calls.append(" ".join(args)))

    wsl.start("alfa")

    assert calls == [
        "--distribution alfa --user root --exec dbus-launch true",
        f"uid={wsl.BOX_UID}",
    ]


def test_registered_matches_whole_names_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """`dev2` must not make `dev` look registered (the Rust port used substrings)."""
    monkeypatch.setattr(wsl, "_capture", lambda *args: "dev2\nUbuntu\n")
    assert wsl.registered("dev2")
    assert not wsl.registered("dev")


def test_running_matches_whole_names_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wsl, "_capture", lambda *args: "ubuntu-dev\n")
    assert wsl.running("ubuntu-dev")
    assert not wsl.running("ubuntu")


def test_user_data_renders_every_hostname_slot() -> None:
    rendered = user_data("alfa")
    assert "hostname=alfa" in rendered
    assert "127.0.1.1       alfa.  alfa" in rendered
    assert "hostnamectl --transient set-hostname alfa" in rendered
    assert "{name}" not in rendered


def test_user_data_creates_the_box_user() -> None:
    rendered = user_data("alfa")
    assert "- name: box" in rendered
    assert rendered.startswith("#cloud-config")


@pytest.mark.skipif(sys.platform == "win32", reason="the guard only fires off Windows")
@pytest.mark.parametrize(
    ("call", "args"),
    [
        (wsl.create, ("alfa",)),
        (wsl.start, ("alfa",)),
        (wsl.stop, ("alfa",)),
        (wsl.delete, ("alfa",)),
        (wsl.connect, ("alfa",)),
        (wsl.list_distributions, ()),
    ],
)
def test_entry_points_refuse_to_run_off_windows(call, args) -> None:
    with pytest.raises(WslError, match="only available on Windows"):
        call(*args)
