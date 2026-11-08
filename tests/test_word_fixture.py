"""A template saved by Microsoft Word (tests/fixtures/word-letter.docx).

Word writes things python-docx samples don't: spell-check marks inside split
placeholders, the address block as one paragraph with Shift+Enter breaks,
8 pt space after every paragraph from the document defaults, and tabs for
first-line indents.
"""
from pathlib import Path

from daisywriter.model import Align, Role
from daisywriter.pipeline import run
from daisywriter.region import apply_regions
from daisywriter.template import load_template

FIXTURE = Path(__file__).parent / "fixtures" / "word-letter.docx"


def test_parse():
    t = apply_regions(load_template(FIXTURE))
    assert not t.issues[:-1]  # only the body-zone info
    assert t.body_source == "auto"
    texts = [p.text for p in t.paragraphs]
    assert texts[2] == ("«FirstName» «LastName»\n«Company»\n«Address1»\n«Address2»\n"
                        "«City», «State»  «Zip»")
    assert "RE: Your order «OrderNumber»" in texts  # placeholder split by w:proofErr
    re_line = t.paragraphs[texts.index("RE: Your order «OrderNumber»")]
    assert re_line.spans[0].bold and re_line.spans[0].text == "RE:"
    assert [p.text.split()[0] for p in t.paragraphs if p.role is Role.BODY] == ["Thank", "Your", "If"]
    assert all(p.space_after_pt == 8 for p in t.paragraphs)  # from w:docDefaults
    assert all(p.align is Align.LEFT for p in t.paragraphs)
    assert t.paragraphs[0].left_pt == 288  # letterhead at 4 in
    assert t.paragraphs[0].default_tab_pt == 36


def test_merge(sample_dir, settings):
    m = run(FIXTURE, sample_dir / "letter-data.xlsx", settings)
    assert m.ok
    lines = [ln.text for ln in m.letters[1].pages[0].lines]
    # Thomas has no Company or Address2: those lines inside the address paragraph go
    i = lines.index("Thomas O'Brien")
    assert lines[i:i + 3] == ["Thomas O'Brien", "88 Harbor Road", "Gloucester, MA  01930"]
    # 8 pt after + an empty paragraph (12 pt) + 8 pt after = 28 pt = 2 blank lines
    assert lines[i + 3:i + 6] == ["", "", "RE: Your order A-10241"]
    # "Sincerely," + two empty paragraphs = 8 + 2 x (12 + 8) = 48 pt = 4 blank lines
    s = next(k for k, x in enumerate(lines) if x.strip() == "Sincerely,")
    assert [x.strip() for x in lines[s + 1:s + 6]] == ["", "", "", "", "Margaret Hollis"]
    # the tab at the start of each body paragraph is a 5-column indent at 10 cpi
    assert any(x.startswith("     Thank you for ordering the Olympia SM9") for x in lines)
