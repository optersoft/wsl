# wslx

Manage Ubuntu **WSL** virtual machines from the command line.

`wslx` imports an Ubuntu rootfs as a WSL distribution, seeds it with cloud-init
(a passwordless-sudo `box` user, the hostname, a few conveniences) and gets you
a shell in it — one command per lifecycle step, no manual `wsl --import`
juggling.

It also manages the machines once they exist: back one up, clone it, move or
compact its disk, publish a port with the firewall rule that goes with it, hand
it a USB device, run a command in it on a schedule, mount a real disk into it.
`wslx --help` lists everything; `wslx gui` opens the same thing as a window.

## Documentation

**All instructions and the tutorial live at
<https://academy.optersoft.com/windows/wsl>.**

## Install

```console
uv tool install wslx
```

With the window (wxPython, a ~20 MB dependency the CLI does not need):

```console
uv tool install "wslx[gui]"
```

or run it without installing:

```console
uvx wslx list
```

`pip install wslx` works too. Python 3.11+, Windows (every command needs
`wsl.exe` on `PATH`).

## Development

```console
uv sync --all-groups
uv run pytest
uv run ruff check
```

The package installs and imports on macOS and Linux so it can be developed and
tested there; the Windows-only paths are covered through their pure helpers
(output parsing, cloud-init rendering, path resolution) and the platform guard.

## License

Licensed under either of [MIT](LICENSE-MIT) or [Apache-2.0](LICENSE-APACHE),
at your option. Unless you state otherwise, any contribution you submit for
inclusion is dual-licensed on those same terms.

Copyright © 2026 Optersoft, S.L.
