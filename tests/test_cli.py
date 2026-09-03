from __future__ import annotations

import pytest
from typer.testing import CliRunner

from wslx import cli, wsl
from wslx.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "wslx" in result.stdout


def test_help_lists_every_command() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("create", "start", "stop", "delete", "list", "connect"):
        assert command in result.stdout


@pytest.mark.parametrize("command", ["create", "start", "stop", "delete"])
def test_commands_apply_to_every_name(monkeypatch: pytest.MonkeyPatch, command: str) -> None:
    seen: list[str] = []
    monkeypatch.setattr(wsl, "_require_windows", lambda: None)
    monkeypatch.setattr(wsl, command, seen.append)

    result = runner.invoke(app, [command, "alfa", "beta"])
    assert result.exit_code == 0, result.output
    assert seen == ["alfa", "beta"]


def test_list_renders_a_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        wsl,
        "list_distributions",
        lambda: [wsl.Distribution("alfa", "Running", "2", default=True)],
    )
    monkeypatch.setattr(wsl, "managed", lambda name: True)

    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "alfa" in result.stdout
    assert "Running" in result.stdout


def test_list_says_so_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wsl, "list_distributions", list)
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "No WSL distributions registered." in result.stdout


def test_connect_forwards_the_new_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, bool]] = []
    monkeypatch.setattr(wsl, "connect", lambda name, new: calls.append((name, new)))

    assert runner.invoke(app, ["connect", "alfa", "--new"]).exit_code == 0
    assert runner.invoke(app, ["connect", "alfa"]).exit_code == 0
    assert calls == [("alfa", True), ("alfa", False)]


def test_errors_do_not_lose_square_brackets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rich reads `[gui]` as markup, which turned the fix into the wrong advice.

    `wslx gui` without wxPython installed tells you to install `wslx[gui]`.
    Printed through rich unescaped, that reached the user as "install wslx" —
    advice that reinstalls exactly what they already have.
    """
    from io import StringIO  # noqa: PLC0415 - only this test needs it

    from rich.console import Console  # noqa: PLC0415

    buffer = StringIO()
    monkeypatch.setattr(cli, "errors", Console(file=buffer, width=200))
    cli.fail('install it with `uv tool install "wslx[gui]"`')
    assert "wslx[gui]" in buffer.getvalue()
