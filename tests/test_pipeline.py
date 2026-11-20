import datetime as dt

import docx

from daisywriter import samples
from daisywriter.issues import Level
from daisywriter.layout import PageNumbers
from daisywriter.pipeline import run
from daisywriter.profile import load_profile


def texts(letter):
    return [ln.text for p in letter.pages for ln in p.lines]


def flat(letter):
    return " ".join(" ".join(texts(letter)).split())


def test_sample_merge(sample_dir, settings):
    m = run(sample_dir / "letter-template.docx", sample_dir / "letter-data.xlsx", settings)
    assert m.ok and len(m.letters) == 5
    t = texts(m.letters[0])
    assert t[0] == "November 8, 2026"
    assert t[2:7] == ["Eleanor Whitfield", "Whitfield & Daughters Stationery", "1427 Maple Avenue",
                      "Suite 200", "Springfield, IL  62704"]
    assert "Dear Eleanor," in t
    assert "Galaxie 12 on October 14. We are" in flat(m.letters[0])
    assert "$89.50" in flat(m.letters[0])
    assert "Shipped:       November 8, 2026" in t
    # Thomas has no company and no Address2: those lines are left out
    t2 = texts(m.letters[1])
    assert t2[2:5] == ["Thomas O'Brien", "88 Harbor Road", "Gloucester, MA  01930"]
    # smart quotes and the em dash become typeable characters
    assert '"A typewriter' in flat(m.letters[0]) and "-- our founder" in flat(m.letters[0])


def test_accents_are_warned(sample_dir, settings):
    m = run(sample_dir / "letter-template.docx", sample_dir / "letter-data.xlsx", settings)
    letter3 = [i for i in m.all_issues() if i.letter == 3 and i.level is Level.WARNING]
    assert any('"é"' in i.message for i in letter3)
    assert "Jose Alvarez" in flat(m.letters[2])


def test_body_marking(sample_dir, settings):
    for name in ("letter-template.docx", "letter-template-markers.docx"):
        m = run(sample_dir / name, sample_dir / "letter-data.xlsx", settings)
        body = [ln.text for p in m.letters[0].pages for ln in p.lines if any(c.body for c in ln.cells)]
        assert body[0].startswith("Thank") and body[-1].startswith("above."), name
        assert not any("{{" in x for x in texts(m.letters[0])), name


def test_unknown_field_suggests_column(tmp_path, settings):
    d = docx.Document()
    d.add_paragraph("Hello {{FristName}}")
    d.save(str(tmp_path / "t.docx"))
    m = run(tmp_path / "t.docx", samples.make_data(tmp_path / "d.xlsx"), settings)
    errors = [i.message for i in m.all_issues() if i.level is Level.ERROR]
    assert errors == ['«FristName» has no matching column in the spreadsheet; did you mean "FirstName"?']
    assert not m.ok


def test_untypeable_character_is_an_error(tmp_path, settings):
    path = samples.make_data(tmp_path / "d.xlsx", rows=[["Ann", "Lee", "Café <Chez>", None, None,
                                                          None, None, None, None, None,
                                                          dt.date(2026, 1, 1), 1]])
    d = docx.Document()
    d.add_paragraph("{{Company}} 50°")
    d.save(str(tmp_path / "t.docx"))
    m = run(tmp_path / "t.docx", path, settings)
    errors = [i.message for i in m.all_issues() if i.level is Level.ERROR]
    assert any('"°"' in e for e in errors)  # the Swintec map has no degree sign yet
    settings.profile = "olympia-electronic-compact-2"
    m = run(tmp_path / "t.docx", path, settings)
    errors = [i.message for i in m.all_issues() if i.level is Level.ERROR]
    assert len(errors) == 2 and all('"<"' in e or '">"' in e for e in errors)  # ° is on this wheel


def test_page_number_format_uses_fields(sample_dir, settings):
    settings.layout.page_numbers = PageNumbers("all", "top", "left", "{{LastName}} - {page}")
    m = run(sample_dir / "letter-template.docx", sample_dir / "letter-data.xlsx", settings)
    assert texts(m.letters[0])[0] == "Whitfield - 1"


def test_profiles_load():
    p = load_profile("olympia-electronic-compact-2")
    assert p.charset["©"] == b"\x0e-\x0f"
    assert not p.can_type("<") and p.can_type("±")


def _format_letter(tmp_path, settings, text):
    d = docx.Document()
    d.add_paragraph(text)
    d.save(str(tmp_path / "f.docx"))
    m = run(tmp_path / "f.docx", samples.make_data(tmp_path / "d.xlsx"), settings)
    return texts(m.letters[0])[0].lstrip()  # python-docx sets 1.25 in margins: a 3-column indent


def test_values_show_as_formatted_in_excel(tmp_path, settings):
    # the sample sheet formats OrderDate as m/d/yyyy and Amount as "$"#,##0.00
    assert _format_letter(tmp_path, settings, "{{OrderDate}} {{Amount}}") == "10/14/2026 $89.50"


def test_template_format_overrides_excel(tmp_path, settings):
    assert _format_letter(tmp_path, settings, "{{OrderDate:MMMM d, yyyy}} {{Amount:0.0}}") == \
        "October 14, 2026 89.5"


def test_excel_formats_can_be_ignored(tmp_path, settings):
    settings.merge.excel_formats = False
    assert _format_letter(tmp_path, settings, "{{OrderDate}} {{Amount}}") == "October 14, 2026 89.5"


def test_case_switch_applies_to_excel_formatted_text(tmp_path, settings):
    assert _format_letter(tmp_path, settings, "{{OrderDate:Upper}}") == "10/14/2026"
    assert _format_letter(tmp_path, settings, "{{LastName:Upper}}") == "WHITFIELD"
