# TODO

## Next up

- [ ] `[human]` The **academy page documents six commands; there are now thirty.**
      `windows/wsl.md` (+ `.ca`/`.es`) still ends at `create`/`connect`/`list`/`delete`,
      and its USB section is a `TODO:` with two links — which `wslx usb` now covers.
      Decide how much of the manager surface belongs in a first-year course page
      before writing it: backup/clone probably yes, `wsl --mount` probably not.
- [ ] Two features remain **unverified on real hardware**, for want of hardware:
      `wslx usb` (the Isard desktop has no usbipd-win and no USB devices to pass
      through) and `wslx mount` / `disks` (one disk, and it is the boot disk, so
      the listing is correctly empty). `move` is untested for the same reason —
      one drive. Everything else, elevated paths included, passes on the
      `windows` desktop; see `Shipped` below.
- [ ] `wslx gui` has no icon and no `.ico`, so the window shows wxPython's
      default. Fine for now, wrong for a screenshot on the academy page.
- [ ] `[human]` **CI cannot run a client Windows.** GitHub hosts Server images
      only, so `windows-2022` / `windows-2025` stand in for the Windows 10 and
      11 codebases. Three things therefore stay desktop-only: an interactive UAC
      prompt (a runner is already elevated, so `compact` and `forward add`
      never raise one there), a Windows edition with no Hyper-V — where
      `compact` must fall back to diskpart, which is the path a student's Home
      laptop takes — and a real USB bus. If that matters more later, a
      self-hosted runner on the Isard desktop is the only way to get it.
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

- 2026-09-03 · Verified end to end on the Isard `windows` desktop (Windows 10
  22H2, Spanish, WSL 2.7.11): 39 of 40 steps green on the first run, then all of
  them. Run as a scheduled task with `RunLevel Highest`, which is what makes the
  elevated paths testable at all — a UAC prompt cannot be answered over SSH, but
  an already-elevated process raises none. `compact` measured: 1321205760 →
  1301282816 bytes, and the tool said "recovered 19.00 MB"
- 2026-09-03 · Four bugs the Mac could not have found, all from that run:
  `compact`/`sparse` could never work (`--terminate` does not detach the disk
  from the shared VM); `elevate_script`'s `chcp 65001` broke diskpart;
  `wsl --shutdown` returns before the disk is free, so compaction needs a
  retry; and the task schedule column was blank on a Spanish Windows, because
  schtasks translates its CSV — the trigger now comes from the task XML
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
