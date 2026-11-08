"""Golden previews: the plain-text preview of each fixture letter, checked in.

Any change to parsing, merging or layout shows up as a readable diff. After an
intended change, regenerate with:  uv run pytest tests/test_golden.py --update-golden
"""
from pathlib import Path

import docx
import pytest

from daisywriter.layout import PageNumbers
from daisywriter.pipeline import run
from daisywriter.preview import render_text

HERE = Path(__file__).parent
GOLDEN = HERE / "golden"


def check(name: str, text: str, request):
    path = GOLDEN / name
    if request.config.getoption("--update-golden"):
        path.write_text(text, encoding="utf-8", newline="\n")
        return
    if not path.exists():
        pytest.fail(f"{path} doesn't exist; create it with --update-golden and review it")
    expected = path.read_text(encoding="utf-8")
    assert text == expected, f"preview differs from {path}; if intended, run with --update-golden"


def preview(m) -> str:
    return render_text(m.letters, len(m.letters), m.profile.line_width)


def long_letter(path):
    d = docx.Document()
    for t in ["{{Today}}", "", "Dear {{FirstName}},", ""]:
        d.add_paragraph(t)
    words = ("Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor "
             "incididunt ut labore et dolore magna aliqua. ")
    for i in range(14):
        d.add_paragraph(f"Paragraph {i + 1}. " + words * (1 + i % 3))
        d.add_paragraph("")
    for t in ["Sincerely,", "", "", "", "Margaret Hollis"]:
        d.add_paragraph(t)
    d.save(str(path))
    return path


def test_word_template(sample_dir, settings, request):
    m = run(HERE / "fixtures" / "word-letter.docx", sample_dir / "letter-data.xlsx", settings)
    check("word-letter.txt", preview(m), request)


def test_generated_template(sample_dir, settings, request):
    m = run(sample_dir / "letter-template.docx", sample_dir / "letter-data.xlsx", settings)
    check("generated-letter.txt", preview(m), request)
    # explicit {{body}} markers give the same letters
    m2 = run(sample_dir / "letter-template-markers.docx", sample_dir / "letter-data.xlsx", settings)
    assert preview(m2) == preview(m)


def test_multi_page_with_page_numbers(sample_dir, settings, request, tmp_path):
    settings.layout.page_numbers = PageNumbers(
        "after_first", "top", "left", "{{FirstName}} {{LastName}}  -  Page {page}  -  {{Today}}")
    m = run(long_letter(tmp_path / "long.docx"), sample_dir / "letter-data.xlsx", settings)
    m.letters = m.letters[:1]
    check("multi-page-letter.txt", preview(m), request)
