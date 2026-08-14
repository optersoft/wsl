# TODO

## Next up

Nothing open.

## Done

- [x] The cloud-init misfire note, cut from README.md in the 2026-08-14 trim, now
      lives on https://academy.optersoft.com/tool/wsl under its own heading,
      *When the seed does not apply* (2026-08-14). The page shows the failure the
      way a user meets it — `wslx start` printing the `WslError` from
      `src/wslx/wsl.py:209`, `cloud-init status` answering `done`, `id -un 1000`
      answering `ubuntu` — and gives the fix, `wslx delete` + `wslx create`, an
      import rather than another download. An aside carries why re-seeding in
      place was tried and dropped (the comment at `wsl.py:230`).
      ⚠️ The content tree is no longer a sibling checkout: it is `pages/` inside
      `~/optersoft/academy`, and the source page is `pages/tool/wsl.md` with
      `.ca`/`.es` variants beside it.
