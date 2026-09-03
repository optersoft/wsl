# TODO

## Next up

- [ ] `[human]` The **academy page documents six commands; there are now thirty.**
      `windows/wsl.md` (+ `.ca`/`.es`) still ends at `create`/`connect`/`list`/`delete`,
      and its USB section is a `TODO:` with two links — which `wslx usb` now covers.
      Decide how much of the manager surface belongs in a first-year course page
      before writing it: backup/clone probably yes, `wsl --mount` probably not.
- [ ] The **elevated paths are untested**: compact, move, mount and `forward add`
      raise a UAC prompt, which cannot be answered over SSH, so the Isard run
      skips them. They need one manual pass in the GUI on a real desktop.
- [ ] `wslx gui` has no icon and no `.ico`, so the window shows wxPython's
      default. Fine for now, wrong for a screenshot on the academy page.
- [ ] Release 0.2.0 once the above two are settled — the version in `pyproject`
      is still 0.1.1, and PyPI's 0.1.1 metadata links `/tool/wsl` (see below).

- [ ] `[human]` `README.md` and the PyPI metadata point at
      <https://academy.optersoft.com/windows/wsl>, which today is the tutorial for
      installing WSL itself, not for `wslx`. Write the wslx page there.
      Do: `academy/pages/windows/wsl.md` (+ `.ca` / `.es` variants beside it)
      Done: the page documents `wslx create` / `connect` / `list` / `delete`
      ⚠️ `pages/tool/wsl.md` already holds that content and names `windows/wsl` as its
      own prerequisite — decide whether it moves, merges or stays before writing.

## Do not "fix" these

- `v0.1.0` tags a 2026-08-04 commit and has no PyPI release behind it — it was
  cut before the repo reached GitHub, so the publish job never ran. Left where
  it is; releases start at 0.1.1.
- wslx 0.1.1 on PyPI links `/tool/wsl`; the fix landed after the upload and
  released metadata is immutable. Corrects itself on the next release, no bump
  just for it.

## Shipped

- 2026-09-03 · The manager surface: `info`, `export`/`restore`/`clone`, `move`,
  `compact`, `sparse`, `default`, `shutdown`, `open`/`terminal`/`code`,
  `forward add|list|remove|repair`, `usb`, `task`, `mount`/`unmount`/`disks`,
  `vm`. New modules `run` (one place that starts Windows programs, and the only
  place that elevates), `registry`, `info`, `backup`, `network`, `usb`,
  `scheduler`, `mount`, `wslconf`, `config`, `integrations`, `report`
- 2026-09-03 · `wslx gui` — a wxPython window over the same core, shipped as the
  `wslx[gui]` extra. Six tabs, one background worker, the core's progress lines
  in a log pane

- 2026-08-14 · README trimmed to install + develop, everything else moved to the
  academy page; `Homepage`/`Documentation` follow it · `01f9141`
- 2026-08-14 · wslx 0.1.1 on PyPI — the first release that actually uploaded,
  via trusted publishing from `optersoft/wsl` · `c74993e` / tag `v0.1.1`
- 2026-08-14 · The cloud-init misfire note now lives on the academy page under
  *When the seed does not apply*, with the `delete` + `create` fix
