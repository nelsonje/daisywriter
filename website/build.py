"""Build the daisywriter web page (published with GitHub Pages).

    uv run python website/build.py --version 0.1.2 --out _site

One page: what daisywriter is, the downloads of the given release, an example
(a Word template, its spreadsheet, and the first letter as the emulator types
it), and the user guide from src/daisywriter/gui/user_guide.md, the same one
the app shows.
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
import tempfile
import tomllib
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
GUIDE = ROOT / "src" / "daisywriter" / "gui" / "user_guide.md"
ICONS = ROOT / "src" / "daisywriter" / "gui" / "icons"
EXAMPLE_TEMPLATE = ROOT / "tests" / "fixtures" / "word-letter.docx"  # typed in Word, with {{placeholders}}
EXAMPLE_COLUMNS = ["FirstName", "LastName", "Company", "City", "Product", "Amount"]
EXAMPLE_ROWS = 3


def guide_html(guide: Path = GUIDE) -> str:
    """The user guide, its headings one level down to sit under the page's own."""
    text = guide.read_text(encoding="utf-8")
    text = re.sub(r"^\# .*\n+", "", text, count=1)  # the page has its own title
    text = re.sub(r"^(#+) ", r"#\1 ", text, flags=re.MULTILINE)
    return markdown.markdown(text, extensions=["tables", "toc"])


TEXT_WIDTH_PT = 6.5 * 72  # Word's default text width (letter, 1-inch margins), for indents


def _paragraph_html(paragraph) -> str:
    style = []
    if paragraph.left_pt:
        style.append(f"margin-left: {100 * paragraph.left_pt / TEXT_WIDTH_PT:.1f}%")
    if paragraph.space_after_pt:
        style.append(f"margin-bottom: {paragraph.space_after_pt:g}pt")
    attr = f' style="{"; ".join(style)}"' if style else ""
    return f"<p{attr}>{_spans_html(paragraph)}</p>"


def _spans_html(paragraph) -> str:
    parts = []
    for s in paragraph.spans:
        text = f"<mark>{{{{{html.escape(s.field.name)}}}}}</mark>" if s.field else html.escape(s.text)
        if s.bold:
            text = f"<b>{text}</b>"
        if s.underline:
            text = f"<u>{text}</u>"
        parts.append(text)
    return "".join(parts) or "&nbsp;"


def _typed_bottom_in(sheet, salutation: str) -> float:
    """Where to crop the typed sheet: below the paragraph after the salutation."""
    rows: dict[int, str] = {}
    for s in sorted(sheet.strikes, key=lambda s: (s.y, s.x)):
        rows[s.y] = rows.get(s.y, "") + s.ch
    ys = sorted(rows)
    at = next(i for i, y in enumerate(ys) if rows[y].strip().startswith(salutation))
    end = at + 1
    while end + 1 < len(ys) and ys[end + 1] - ys[end] <= 2:  # the next line, at 6 lines per inch
        end += 1
    if end + 1 < len(ys):  # into the next paragraph, which fades out
        end += 1
    return (ys[end] + 3) / 12


def example(out: Path) -> str:
    """The "How it works" section, and the typed letter as out/example-letter.svg."""
    from daisywriter import samples
    from daisywriter.excelfmt import format_excel
    from daisywriter.job import PrintOptions
    from daisywriter.model import Role
    from daisywriter.pipeline import run
    from daisywriter.svg import sheet_svg
    from daisywriter.transports.emulator import emulate

    with tempfile.TemporaryDirectory() as tmp:
        data = samples.make_data(Path(tmp) / "letter-data.xlsx")
        m = run(EXAMPLE_TEMPLATE, data)
    first_body = next(p for p in m.template.paragraphs if p.role is Role.BODY)
    salutation = next(p for p in m.template.paragraphs if p.role is Role.SALUTATION)
    doc = "".join(_paragraph_html(p) for p in m.template.paragraphs if p.index <= first_body.index)

    def cell(record, column):
        value = record.values.get(column)
        shown = format_excel(value, record.formats.get(column)) if value is not None else ""
        return html.escape(shown if shown is not None else str(value))
    head = "".join(f"<th>{html.escape(c)}</th>" for c in EXAMPLE_COLUMNS)
    rows = "".join("<tr>" + "".join(f"<td>{cell(r, c)}</td>" for c in EXAMPLE_COLUMNS) + "<td></td></tr>"
                   for r in m.dataset.records[:EXAMPLE_ROWS])

    letter = m.letters[0]
    lay = m.settings.layout
    sheet = emulate([letter], m.profile, PrintOptions.for_profile(
        m.profile, stock=lay.stock, top_lines=lay.top_lines)).sheets[0]
    name = salutation.text.split()[0]
    (out / "example-letter.svg").write_text(sheet_svg(
        sheet, lay.stock, top_in=0.5, bottom_in=_typed_bottom_in(sheet, name), left_in=0.6, right_in=7.9,
        title=f"The top of the letter to {letter.record.values['FirstName']}, as daisywriter types it"),
        encoding="utf-8")
    return f"""<div class="steps">
  <figure>
    <figcaption><span class="n">1</span> Write the letter in Word. Where something changes from
    person to person, type the column's name in double braces.</figcaption>
    <div class="doc">
{doc}
    </div>
  </figure>
  <figure>
    <figcaption><span class="n">2</span> List the people in Excel: the column names in the first
    row, then one row per letter.</figcaption>
    <div class="table"><table>
      <tr>{head}<th>…</th></tr>
      {rows}
    </table></div>
  </figure>
  <figure>
    <figcaption><span class="n">3</span> daisywriter types a letter for each row. This is the
    first one, as its typewriter emulator draws it.</figcaption>
    <div class="typed"><img src="example-letter.svg"
      alt="The top of the typed letter to {html.escape(str(letter.record.values['FirstName']))}"></div>
  </figure>
</div>"""


def build(version: str, out: Path, repo: str, guide: Path = GUIDE) -> Path:
    base = f"https://github.com/{repo}"
    download = f"{base}/releases/download/v{version}/daisywriter-{version}"
    out.mkdir(parents=True, exist_ok=True)
    page = string.Template((HERE / "index.html").read_text(encoding="utf-8")).substitute(
        version=html.escape(version),
        example=example(out),
        msi=f"{download}-windows-x64.msi",
        dmg=f"{download}-macos-arm64.dmg",
        samples=f"{download}-samples.zip",
        notes=f"{base}/releases/tag/v{version}",
        repo=base,
        guide=guide_html(guide),
    )
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
