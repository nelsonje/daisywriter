# daisywriter: notes for Claude

Mail merge (Word template + Excel data) typed on daisywheel typewriters (Swintec 1146 CMP,
Olympia Electronic Compact 2). `docs/PLAN.md` is the design doc: read it before larger changes,
and keep it current.

## Rules
- **Commits use `jacob@jfet.net` only.** Once per clone:
  `git config user.email jacob@jfet.net` and `git config core.hooksPath .githooks`.
  The hooks and CI's `emails` job accept only that address and GitHub's noreply addresses.
  Keep them as an allow-list, and never write another address or domain into the repository.
- **Office files:** a .docx/.xlsx saved on a managed machine can carry a hidden sensitivity label
  (`docMetadata/LabelInfo.xml`, with the organisation's ID). Strip it, with its entries in
  `_rels/.rels` and `[Content_Types].xml`, before committing. Prefer generated files
  (`daisywriter make-samples`).
- **The typewriter is driven directly** through the USB-parallel adapter (PL2305, 067b:2305):
  usbprint.sys via ctypes on Windows, pyusb/libusb elsewhere. Never through a printer, print
  queue or spooler.
- **No force-pushes or history rewrites** without explicit approval. Work on a branch; `main`
  is what releases are tagged from.

## Commands
```sh
uv sync
uv run pytest                                   # GUI tests run offscreen
uv run ruff check src tests
uv run daisywriter make-samples samples         # sample templates and data (samples/ is ignored)
uv run daisywriter status                       # adapter found? on-line?
uv run daisywriter testpage margins format bold
uv run daisywriter print TEMPLATE DATA --letters 1 [--emulate out.pdf | --dry-run out.bin]
uv run daisywriter-gui
```
Use `uv run` inside the repository: an installed release also puts `daisywriter` on PATH.
CI builds the Windows MSI and the Mac DMG; there's no need to build them locally.

## Hardware checks
`docs/PLAN.md` §16.1 is the checklist for sessions with the typewriter, and §16 holds the
results. Record each result there with the date and which unit was used. Before each step that
needs a hand on the machine (loading paper, pressing ON LINE, pulling the cable), tell the user
what to do and what to look for on the paper.

## Releases
`docs/releases/README.md`: bump `version` in `pyproject.toml`, add `docs/releases/v<version>.md`,
then `git tag v<version> && git push origin v<version>`. CI publishes the release.
