# wslx

Manage Ubuntu **WSL** virtual machines from the command line.

`wslx` imports an Ubuntu Noble rootfs as a WSL distribution, seeds it with
cloud-init (a passwordless-sudo `box` user, the hostname, a few conveniences)
and gets you a shell in it — one command per lifecycle step, no manual
`wsl --import` juggling.

It is a Python port of the `box wsl` provider from
[gitlab.com/xtec/box](https://gitlab.com/xtec/box), packaged on its own so it
installs with `uv`/`pip` instead of a Rust toolchain. Machines created by
either tool are interchangeable: same rootfs, same cloud-init, same `box` user.

## Install

```console
uv tool install wslx
```

or run it without installing:

```console
uvx wslx list
```

`pip install wslx` works too. Python 3.11+.

## Use

```console
wslx create alfa          # import a new Ubuntu distribution named alfa
wslx connect alfa         # open a shell in it (starts it if needed)
wslx connect beta --new   # create, start and enter in one step
wslx list                 # every registered distribution
wslx stop alfa            # terminate
wslx delete alfa          # unregister and remove its disk
```

`create`, `start`, `stop` and `delete` take any number of names:

```console
wslx create alfa beta gamma
```

## What a machine looks like

Inside every distribution wslx creates:

- user **`box`**, password `password`, passwordless `sudo`, UID 1000 and the
  default login user
- hostname set to the distribution name (in `/etc/wsl.conf`, `/etc/hostname`
  and `/etc/hosts`)
- `install-docker` alias — `curl -L sh.xtec.dev/docker.sh | sh`

## Where things live

| What | Where |
|---|---|
| Distribution disks (`ext4.vhdx`) | `%APPDATA%\wslx\<name>\` |
| Downloaded rootfs image | `%APPDATA%\wslx\cache\` |
| cloud-init user-data | `%USERPROFILE%\.cloud-init\<name>.user-data` |

`wslx delete` removes all three for the distribution it deletes.

`wslx list` shows every registered WSL distribution, not just the ones wslx
made — the **Managed** column tells you which ones it owns. Deleting an
unmanaged distribution still unregisters it, but its disk lives wherever its
own installer put it.

## Requirements

WSL only exists on Windows: every command needs `wsl.exe` on `PATH` and fails
with a clear message anywhere else. The package still installs and imports on
macOS and Linux so it can be developed and tested there.

## Development

```console
uv sync --all-groups
uv run pytest
uv run ruff check
```

The test suite is platform-independent — the Windows-only paths are covered
through their pure helpers (output parsing, cloud-init rendering, path
resolution) and the platform guard itself.

## License

AGPL-3.0-only. © David de Mingo.
