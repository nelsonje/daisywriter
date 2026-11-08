import docx
import pytest

from daisywriter import samples
from daisywriter.issues import Level
from daisywriter.model import Align, Span
from daisywriter.template import load_template, parse_field_instruction, split_placeholders


def by_text(template, needle):
    return next(p for p in template.paragraphs if needle in p.text)


def test_fields_from_both_syntaxes(sample_dir):
    t = load_template(sample_dir / "letter-template.docx")
    names = [f.name for f in t.fields()]
    # MERGEFIELDs (complex and simple) and {{placeholders}}, in order of first use
    assert names[:4] == ["FirstName", "LastName", "Company", "Address1"]
    assert {"OrderNumber", "Product", "OrderDate", "Amount", "Today"} <= set(names)
    sources = {f.name: f.source for f in t.fields()}
    assert sources["FirstName"] == "mergefield" and sources["Product"] == "placeholder"


def test_date_field_and_split_placeholder(sample_dir):
    t = load_template(sample_dir / "letter-template.docx")
    date = t.paragraphs[0].spans[0].field
    assert date.source == "date" and date.picture == "MMMM d, yyyy"
    # "Dear {{First" + "Name}}," was typed across two runs
    assert by_text(t, "Dear").text == "Dear «FirstName»,"


def test_formatting_alignment_indents_tabs(sample_dir):
    t = load_template(sample_dir / "letter-template.docx")
    re_line = by_text(t, "Re:")
    assert re_line.spans[0].bold and re_line.spans[0].text == "Re:"
    fabric = by_text(t, "fabric")
    assert [s.text for s in fabric.spans if s.bold] == ["fabric"]
    assert [s.text for s in fabric.spans if s.underline] == ["not"]
    assert by_text(t, "Thank you").align is Align.JUSTIFY
    quote = by_text(t, "outlast")
    assert quote.left_pt == 36 and quote.right_pt == 36
    order = by_text(t, "Order number")
    assert order.tab_stops_pt == (108.0,)
    assert "\t" in order.text and "\n" in order.text


def test_header_is_ignored_with_info(sample_dir):
    t = load_template(sample_dir / "letter-template.docx")
    assert not any("HOLLIS" in p.text for p in t.paragraphs)
    assert any(i.level is Level.INFO and "header" in i.message for i in t.issues)


def test_parse_field_instruction_switches():
    kind, ref = parse_field_instruction(r' MERGEFIELD "First Name" \* Upper \b "Attn: " ')
    assert kind == "MERGEFIELD"
    assert (ref.name, ref.case, ref.before) == ("First Name", "upper", "Attn: ")
    kind, ref = parse_field_instruction(r'MERGEFIELD Total \# "$#,##0.00"')
    assert (ref.picture, ref.kind) == ("$#,##0.00", "number")
    assert parse_field_instruction("NEXT")[0] == "NEXT"


def test_split_placeholders_keeps_formatting():
    spans = split_placeholders([Span("Hello {{Na", bold=True), Span("me:upper}} and «Other»!")])
    assert [(s.text, s.field and s.field.name, s.bold) for s in spans] == [
        ("Hello ", None, True), ("", "Name", True), (" and ", None, False),
        ("", "Other", False), ("!", None, False)]
    assert spans[1].field.case == "upper"


def _doc_with(tmp_path, build):
    d = docx.Document()
    build(d)
    path = tmp_path / "t.docx"
    d.save(str(path))
    return load_template(path)


def test_unsupported_content_is_reported(tmp_path):
    def build(d):
        d.add_paragraph("Hello")
        d.add_table(rows=1, cols=2)
        p = d.add_paragraph()
        samples.add_field(p, "NEXT", "")
        p = d.add_paragraph("Broken {{Name}")
    t = _doc_with(tmp_path, build)
    messages = [(i.level, i.message) for i in t.issues]
    assert any(lvl is Level.ERROR and "tables" in m for lvl, m in messages)
    assert any(lvl is Level.ERROR and "NEXT" in m for lvl, m in messages)
    assert any(lvl is Level.WARNING and "{{" in m for lvl, m in messages)


def test_hyperlink_field_keeps_its_text(tmp_path):
    def build(d):
        p = d.add_paragraph("See ")
        samples.add_field(p, 'HYPERLINK "https://example.com"', "our website")
    t = _doc_with(tmp_path, build)
    assert t.paragraphs[0].text == "See our website"


def test_style_inheritance(tmp_path):
    def build(d):
        d.styles["Normal"].font.bold = True
        p = d.add_paragraph()
        p.add_run("bold by style")
        p.add_run(" not bold").bold = False
    t = _doc_with(tmp_path, build)
    assert [(s.text, s.bold) for s in t.paragraphs[0].spans] == [
        ("bold by style", True), (" not bold", False)]


def test_not_a_docx(tmp_path):
    bad = tmp_path / "bad.docx"
    bad.write_text("nope", encoding="utf-8")
    with pytest.raises(ValueError, match="isn't a readable"):
        load_template(bad)
