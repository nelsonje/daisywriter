"""The web page: website/build.py with the user guide."""
import re
import runpy
from pathlib import Path

build = runpy.run_path(str(Path(__file__).parent.parent / "website" / "build.py"))["build"]


def test_page_links_to_the_release_and_has_the_guide(tmp_path):
    page = build("0.1.2", tmp_path, "someone/daisywriter").read_text(encoding="utf-8")
    base = "https://github.com/someone/daisywriter/releases/download/v0.1.2/daisywriter-0.1.2"
    for suffix in ("-windows-x64.msi", "-macos-arm64.dmg"):
        assert f'class="button" href="{base}{suffix}"' in page  # a button each
    assert f'href="{base}-samples.zip"' in page
    assert "Version 0.1.2" in page and not re.search(r"\$\{?[a-z_]+", page)  # every placeholder filled
    # the guide, a level below the page's headings, with its tables
    assert "<h1>daisywriter</h1>" in page and "daisywriter user guide" not in page
    assert '<h3 id="5-print">5. Print</h3>' in page and "<table>" in page
    assert '<a href="https://github.com/someone/daisywriter/blob/main/LICENSE">MIT license</a>' in page
    assert page.index('id="about"') > page.index('id="guide"')  # at the end, after the guide
    assert {p.name for p in tmp_path.iterdir()} == {"index.html", "style.css", "icon.png", "favicon.png",
                                                    "example-letter.svg"}


def test_example_of_a_typed_letter(tmp_path):
    page = build("0.1.2", tmp_path, "someone/daisywriter").read_text(encoding="utf-8")
    how = page[page.index('<section id="how">'):page.index('<section id="needs">')]
    assert "<mark>{{FirstName}}</mark>" in how and "<td>Eleanor</td>" in how and "<td>$89.50</td>" in how
    svg = (tmp_path / "example-letter.svg").read_text(encoding="utf-8")
    assert svg.startswith("<svg") and 'aria-label="The top of the letter to Eleanor' in svg
    # cropped: the first paragraph of the body is there, the closing isn't
    typed = "".join(re.findall(r">([^<])</text>", svg))
    assert "parcelpost." in typed and "Sincerely" not in typed
