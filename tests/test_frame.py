"""Paper size and margins: Word's page setup fitted to the typewriter."""
import docx
import pytest
from docx.shared import Inches

from daisywriter import issues as I
from daisywriter import samples
from daisywriter.frame import fit_page
from daisywriter.job import PrintOptions, sheet_prompt
from daisywriter.model import PageSetup
from daisywriter.pdf import write_pdf
from daisywriter.pipeline import run
from daisywriter.profile import LETTER, inches, load_profile, paper_size
from daisywriter.template import load_template
from daisywriter.testpage import left_page
from daisywriter.transports.emulator import STEPS_PER_INCH, emulate

SWINTEC = load_profile("swintec-1146cmp")


def page(width=8.5, length=11.0, left=1.0, right=1.0, top=1.0, bottom=1.0):
    return PageSetup(width, length, left, right, top, bottom)


def messages(issues, level):
    return [i.message for i in issues if i.level is level]


def test_letter_with_one_inch_margins():
    frame, issues = fit_page(page(), SWINTEC)
    assert (frame.stock, frame.indent, frame.width, frame.top_lines, frame.bottom_lines,
            frame.shift_in) == (LETTER, 0, 65, 6, 6, 0.0)
    assert issues == []
    assert frame.describe(SWINTEC) == "Letter (8½ × 11 in), margins 1 in, 65 characters per line"


def test_narrow_paper():
    frame, issues = fit_page(page(width=6.125), SWINTEC)
    assert (frame.stock.width_in, frame.indent, frame.width) == (6.125, 0, 41)
    assert issues == []
    assert frame.describe(SWINTEC) == "6⅛ × 11 in, margins 1 in, 41 characters per line"


def test_wider_left_margin_indents():
    frame, issues = fit_page(page(left=1.5, right=1.25), SWINTEC)
    assert (frame.indent, frame.width, frame.shift_in) == (5, 57, 0.0)
    assert frame.margins_in(SWINTEC) == (1.5, 1.25, 1.0, 1.0)  # as in Word
    assert issues == []


def test_narrower_left_margin_moves_the_sheet():
    frame, issues = fit_page(page(left=0.75, right=1.25), SWINTEC)
    assert (frame.indent, frame.width, frame.shift_in) == (0, 65, 0.25)
    assert frame.margins_in(SWINTEC)[0] == pytest.approx(0.75)
    assert messages(issues, I.Level.WARNING) == [
        ("the left margin in Word (¾ in) is narrower than the typewriter's (1 in): "
        "put each sheet ¼ inch to the right of the paper guide (or of 10 on the scale)")]
    opts = PrintOptions.for_profile(SWINTEC, frame)
    assert ("Put its left edge ¼ inch to the right of the paper guide (or of 10 on the scale)."
            in sheet_prompt(opts, "letter 1"))
    assert "against the paper guide (or at 10 on the scale)" in sheet_prompt(PrintOptions(), "letter 1")


def test_a_left_margin_within_half_a_column_needs_no_move():
    frame, issues = fit_page(page(left=0.984, right=0.984), SWINTEC)  # 2.5 cm
    assert (frame.shift_in, frame.indent, frame.width) == (0.0, 0, 65)
    assert issues == []


def test_lines_never_reach_past_the_typewriters_right_margin():
    frame, issues = fit_page(page(left=1.0, right=0.5), SWINTEC)
    assert frame.columns == SWINTEC.line_width == 66
    assert messages(issues, I.Level.WARNING) == [
        ("the right margin in Word (½ in) is narrower than the typewriter allows, so lines end "
        "7.6 in from the sheet's left edge (a 0.9 in right margin)")]


def test_top_margin_is_at_least_where_a_loaded_sheet_is_typed():
    frame, issues = fit_page(page(top=0.5, bottom=0.5), SWINTEC)
    assert (frame.top_lines, frame.bottom_lines) == (SWINTEC.load_offset_lines, 3)
    assert "the letter starts ⅔ in down" in messages(issues, I.Level.WARNING)[0]


def test_margins_that_leave_no_room_are_errors():
    _, issues = fit_page(page(width=4, left=1.5, right=1.5), SWINTEC)
    assert messages(issues, I.Level.ERROR) == ["the margins leave room for only 10 characters per line"]
    _, issues = fit_page(page(top=5, bottom=5.5), SWINTEC)
    assert messages(issues, I.Level.ERROR) == ["the top and bottom margins leave room for only 3 lines"]


def test_overrides_and_no_page_setup():
    frame, _ = fit_page(None, SWINTEC)
    assert (frame.stock, frame.indent, frame.width, frame.top_lines) == (LETTER, 0, 66, 6)
    frame, _ = fit_page(page(), SWINTEC, "legal", top_lines=8, bottom_lines=3)
    assert (frame.stock.name, frame.top_lines, frame.bottom_lines, frame.width) == ("legal", 8, 3, 65)


def test_paper_sizes_and_inches():
    assert paper_size("Letter") is LETTER
    assert paper_size("8.5x11") is LETTER
    custom = paper_size("6.125 × 11")
    assert (custom.name, custom.width_in, custom.length_in) == ("custom", 6.125, 11.0)
    assert custom.label == "6⅛ × 11 in"
    assert paper_size("a4").label == "A4 (8.27 × 11.69 in)"
    with pytest.raises(ValueError, match="unknown paper size"):
        paper_size("6.125")
    assert [inches(x) for x in (1, 0.75, 6.125, 8.27, 2 / 3, 0.9, 0)] == ["1", "¾", "6⅛", "8.27", "⅔", "0.9", "0"]


def narrow_template(path, width=6.125, left=1.0):
    samples.make_template(path)
    d = docx.Document(str(path))
    for section in d.sections:
        section.page_width = Inches(width)
        section.left_margin = Inches(left)
    d.save(str(path))
    return path


def test_template_page_setup(tmp_path):
    t = load_template(narrow_template(tmp_path / "narrow.docx"))
    assert t.page == PageSetup(6.125, 11.0, 1.0, 1.0, 1.0, 1.0)
    d = docx.Document(str(tmp_path / "narrow.docx"))
    d.add_section().page_width = Inches(8.5)
    d.save(str(tmp_path / "two.docx"))
    t = load_template(tmp_path / "two.docx")
    assert t.page.width_in == 6.125
    assert any("different paper sizes or margins" in i.message for i in t.issues)


def test_a_narrow_letter_types_inside_its_margins(tmp_path, settings):
    m = run(narrow_template(tmp_path / "narrow.docx"), samples.make_data(tmp_path / "d.xlsx"), settings)
    assert m.ok
    assert m.frame.width == 41
    assert any(i.message.startswith("6⅛ × 11 in, margins 1 in") for i in m.issues)
    assert all(len(ln.cells) <= 41 for letter in m.letters for p in letter.pages for ln in p.lines)
    opts = PrintOptions.for_profile(m.profile, m.frame)
    assert sheet_prompt(opts, "letter 1").startswith("Insert a sheet of 6⅛ × 11 in paper for letter 1")
    e = emulate(m.letters[:1], m.profile, opts)
    assert e.events == []
    cols = {s.x * SWINTEC.pitch_cpi // STEPS_PER_INCH for s in e.sheets[0].strikes}
    assert min(cols) == 10 and max(cols) <= 50  # 1 in from each edge of a 6⅛ in sheet
    write_pdf(tmp_path / "narrow.pdf", e.sheets, opts.stock)
    assert b"/MediaBox [0 0 441.00 792.00]" in (tmp_path / "narrow.pdf").read_bytes()


def test_a_wider_left_margin_starts_lines_further_in(tmp_path, settings):
    m = run(narrow_template(tmp_path / "n.docx", left=1.5), samples.make_data(tmp_path / "d.xlsx"), settings)
    e = emulate(m.letters[:1], m.profile, PrintOptions.for_profile(m.profile, m.frame))
    cols = {s.x * SWINTEC.pitch_cpi // STEPS_PER_INCH for s in e.sheets[0].strikes}
    assert min(cols) == 15 and max(cols) <= 50
    assert e.events == []


def test_left_page_lines_up_on_the_emulator():
    from daisywriter.layout import Page
    from daisywriter.merge import Letter
    from daisywriter.records import Record
    letter = Letter(0, Record(0, {}), [], pages=[Page(1, left_page(SWINTEC).lines)])
    e = emulate([letter], SWINTEC)
    bars = [s.x * SWINTEC.pitch_cpi // STEPS_PER_INCH for s in e.sheets[0].strikes if s.ch == "|"]
    assert bars == [SWINTEC.margin_left] * 5
    assert min(s.x for s in e.sheets[0].strikes) * SWINTEC.pitch_cpi // STEPS_PER_INCH == 2
    assert e.events == []
