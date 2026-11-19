# Release notes

Pushing a tag `v<version>` (matching `version` in `pyproject.toml`) makes CI build
the Windows installer, the Mac disk image and `daisywriter-<version>-samples.zip`
(the sample letters, with `packaging/samples-README.txt`) and publish them as a
GitHub release, with the notes in `v<version>.md` from this folder. Versions
before 1.0 are marked as pre-releases. List all three under Downloads in the
notes.

To release:
1. Set `version` in `pyproject.toml` (and run `uv lock`), and write `docs/releases/v<version>.md`.
2. Commit and merge to main, then: `git tag v<version> && git push origin v<version>`.

Each release needs a new version number: Windows only upgrades an installed copy
to a higher version.
