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
- [ ] `[human]` **CI cannot run a client Windows**, and three things therefore
      stay desktop-only: an interactive UAC prompt (a runner is already
      elevated, so `compact` and `forward add` never raise one there), a
      Windows edition with no Hyper-V — where `compact` must fall back to
      diskpart, the path a student's Home laptop takes — and a real USB bus.
      A self-hosted runner on the Isard desktop is the only way to get those.
      Everything else does run on both images; see below.
- [ ] `[human]` **PyPI's 0.2.0 metadata points `Documentation` at the academy
      page**, which still documents six commands out of thirty. Nothing to fix
      in the package — released metadata is immutable — but it is the first
      thing a new user reads, so the page is now the long pole.

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

- 2026-09-03 · **wslx 0.2.0 on PyPI**, published by the tag `v0.2.0` over
  trusted publishing — so the `optersoft/wsl` publisher is confirmed correct
  after the return to GitHub, which had not been re-verified. Both artifacts
  uploaded; `uvx --from "wslx[gui]==0.2.0"` resolves wxPython. ⚠️ The index
  lags the JSON API by a minute or two: the first `uvx` after a release can
  say "no version of wslx==0.2.0", which is propagation, not a failed upload
- 2026-09-03 · Rich was eating the brackets in `wslx gui`'s own advice — it
  told people to install `wslx[gui]` and printed "install wslx", the one word
  that made it wrong. Errors and the name column are escaped now. Found by
  running the built artifact, and nearly missed because
  `uv run --with <local wheel>` caches by version and kept re-testing the
  previous build; the publish job's smoke steps pass `--no-cache`
- 2026-09-03 · **The full live suite runs on both GitHub images.** There is no
  Windows 10 or 11 runner — only Server — so the matrix is `windows-2022`
  (build 20348, the Win10 21H2 codebase) and `windows-2025` (build 26100, the
  Win11 24H2 codebase). 2022 ships the inbox `wsl.exe`, but **both optional
  features are already enabled on that image**, so installing the WSL MSI
  in-job brings up 2.7.11 with kernel 6.18 and **no restart** — which the fleet
  notes said was impossible. A skip on either image is now a hard failure.
- 2026-09-03 · That runner found a bug nothing else could: its
  `wsl --status` default version is **1**, and `wslx create` did not pass
  `--version 2`, so it built a WSL 1 machine — no systemd, no cloud-init, no
  box user — and said nothing, because a WSL 1 distribution has no `ext4.vhdx`
  so `managed` returned False and the seed check never fired. CI deliberately
  leaves that default at 1 and asserts the import was version 2 from the
  registry; it is the only place this reproduces.
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
