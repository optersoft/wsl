# TODO

## Next up

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

- 2026-08-14 · README trimmed to install + develop, everything else moved to the
  academy page; `Homepage`/`Documentation` follow it · `01f9141`
- 2026-08-14 · wslx 0.1.1 on PyPI — the first release that actually uploaded,
  via trusted publishing from `optersoft/wsl` · `c74993e` / tag `v0.1.1`
- 2026-08-14 · The cloud-init misfire note now lives on the academy page under
  *When the seed does not apply*, with the `delete` + `create` fix
