"""Build the daisywriter web page (published with GitHub Pages).

    uv run python website/build.py --version 0.1.2 --out _site

One page: what daisywriter is, the downloads of the given release, and the
user guide from src/daisywriter/gui/user_guide.md, the same one the app shows.
The download links name the release's files: GitHub's "latest release" links
skip pre-releases, which every 0.x version is.
"""
from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import string
import tomllib
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
GUIDE = ROOT / "src" / "daisywriter" / "gui" / "user_guide.md"
ICONS = ROOT / "src" / "daisywriter" / "gui" / "icons"


def guide_html(guide: Path = GUIDE) -> str:
    """The user guide, its headings one level down to sit under the page's own."""
    text = guide.read_text(encoding="utf-8")
    text = re.sub(r"^\# .*\n+", "", text, count=1)  # the page has its own title
    text = re.sub(r"^(#+) ", r"#\1 ", text, flags=re.MULTILINE)
    return markdown.markdown(text, extensions=["tables", "toc"])


def build(version: str, out: Path, repo: str, guide: Path = GUIDE) -> Path:
    base = f"https://github.com/{repo}"
    download = f"{base}/releases/download/v{version}/daisywriter-{version}"
    page = string.Template((HERE / "index.html").read_text(encoding="utf-8")).substitute(
        version=html.escape(version),
        msi=f"{download}-windows-x64.msi",
        dmg=f"{download}-macos-arm64.dmg",
        samples=f"{download}-samples.zip",
        notes=f"{base}/releases/tag/v{version}",
        repo=base,
        guide=guide_html(guide),
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page, encoding="utf-8")
    shutil.copy(HERE / "style.css", out / "style.css")
    shutil.copy(ICONS / "daisywriter-256.png", out / "icon.png")
    shutil.copy(ICONS / "daisywriter-32.png", out / "favicon.png")
    return out / "index.html"


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the daisywriter web page.")
    ap.add_argument("--version", help="the release to link to (default: pyproject.toml's version)")
    ap.add_argument("--out", type=Path, default=Path("_site"))
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "nelsonje/daisywriter"))
    ap.add_argument("--guide", type=Path, default=GUIDE,
                    help="the user guide to include (the release's own, in CI)")
    a = ap.parse_args()
    version = a.version or tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    print(f"wrote {build(version.removeprefix('v'), a.out, a.repo, a.guide)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
