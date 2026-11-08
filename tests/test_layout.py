import pytest

from daisywriter.layout import (
    Cell,
    LayoutSettings,
    Line,
    PageNumbers,
    _Block,
    layout_letter,
    paginate,
    wrap_paragraph,
)
from daisywriter.model import Align, Paragraph, Role, Span
from daisywriter.profile import load_profile

PROFILE = load_profile("swintec-1146cmp")  # 10 cpi, 6 lpi, 64 columns
W = PROFILE.line_width


def lines(text, settings=None, **kw):
    spans = kw.pop("spans", None) or [Span(text)]
    p = Paragraph(spans, 1, **kw)
    issues = []
    out = [ln.text for ln, _ in wrap_paragraph(p, PROFILE, settings or LayoutSettings(), issues, "p1")]
    return out, issues


WORDS = ("The quick brown fox jumps over the lazy dog and keeps running far beyond the "
         "edge of the meadow until it reaches the river.")


def test_width():
    assert W == 64


def test_wrap_left():
    out, _ = lines(WORDS)
    assert all(len(x) <= W for x in out)
    assert " ".join(out) == WORDS
    assert out[0] == "The quick brown fox jumps over the lazy dog and keeps running far"[:len(out[0])]
    assert len(out[0]) + 1 + len(out[1].split()[0]) > W  # greedy: next word didn't fit


def test_word_breaks_ignore_source_line_breaks_but_keep_manual_ones():
    out, _ = lines("one two\nthree")
    assert out == ["one two", "three"]


def test_center_and_right():
    out, _ = lines("centered", align=Align.CENTER)
    assert out == [" " * ((W - 8) // 2) + "centered"]
    out, _ = lines("right", align=Align.RIGHT)
    assert out == [" " * (W - 5) + "right"]


def test_justify_fills_every_line_but_the_last():
    out, _ = lines(WORDS, align=Align.JUSTIFY)
    assert all(len(x) == W for x in out[:-1])
    assert "  " not in out[-1]
    out, _ = lines(WORDS, LayoutSettings(justify=False), align=Align.JUSTIFY)
    assert all("  " not in x for x in out)


def test_indents():
    # 0.5 in = 5 columns at 10 cpi
    out, _ = lines(WORDS, left_pt=36, right_pt=36)
    assert all(x.startswith("     ") and len(x) <= W - 5 for x in out)
    out, _ = lines(WORDS, first_line_pt=36)
    assert out[0].startswith("     The") and out[1][0] != " "
    out, _ = lines("1.\tHanging indent text that wraps onto a second line, which should line up "
                   "under the text and not the number.", left_pt=36, first_line_pt=-36)
    assert out[0].startswith("1.   Hanging")
    assert all(x.startswith("     ") and x[5] != " " for x in out[1:])


def test_tabs():
    out, _ = lines("a\tb")
    assert out == ["a    b"]  # default stops every 0.5 in
    out, _ = lines("Label:\tvalue", tab_stops_pt=(108.0,))
    assert out == ["Label:         value"]


def test_hyphen_break_and_overlong_word():
    out, _ = lines("x" * 57 + " well-known")
    assert out == ["x" * 57 + " well-", "known"]
    out, issues = lines("y" * 70)
    assert out == ["y" * 64, "y" * 6]
    assert issues and "longer than the line" in issues[0].message


def test_formatting_carries_into_cells():
    p = Paragraph([Span("plain "), Span("bold", bold=True), Span(" under", underline=True)], 1)
    (ln, _), = wrap_paragraph(p, PROFILE, LayoutSettings(), [], "")
    assert [c.bold for c in ln.cells[6:10]] == [True] * 4
    assert all(c.underline for c in ln.cells[10:])


def test_empty_paragraph_is_one_blank_line():
    out, _ = lines("")
    assert out == [""]


def blocks_of(sizes, **kw):
    return [_Block([Line([Cell("x")]) for _ in range(n)], kw.get("gap", 0)) for n in sizes]


def test_paginate_simple_and_widow_orphan():
    pages = paginate(blocks_of([5, 5]), lambda page: 8)
    assert [len(p) for p in pages] == [8, 2]  # second block splits 3 + 2
    pages = paginate(blocks_of([7, 3]), lambda page: 8)
    assert [len(p) for p in pages] == [7, 3]  # a 3-line block can't split 1 + 2


def test_keep_with_next_moves_chain():
    bl = blocks_of([5, 1, 2])
    bl[1].keep_with_next = True  # "Sincerely," stays with the signature
    pages = paginate(bl, lambda page: 7)
    assert [len(p) for p in pages] == [5, 3]


def test_forced_page_break():
    x = [Cell("x")]
    out = paginate([_Block([Line(x)], 0, page_after=True), _Block([Line(x)], 0)], lambda p: 50)
    assert len(out) == 2


def letter_paras(n):
    paras = [Paragraph([Span(WORDS)], i, space_after_pt=12) for i in range(1, n + 1)]
    paras.append(Paragraph([Span("Sincerely,")], n + 1, role=Role.CLOSING))
    paras.append(Paragraph([Span("")], n + 2, role=Role.CLOSING))
    paras.append(Paragraph([Span("Ann")], n + 3, role=Role.CLOSING))
    return paras


def test_spacing_becomes_blank_lines():
    pages, _ = layout_letter(letter_paras(2), PROFILE, LayoutSettings())
    texts = [ln.text for ln in pages[0].lines]
    assert texts[2] == "" and texts[3].startswith("The")  # 12 pt after = one blank line


@pytest.mark.parametrize("position", ["top", "bottom"])
def test_page_numbers(position):
    s = LayoutSettings(page_numbers=PageNumbers("after_first", position, "right", "Page {page}"))
    pages, issues = layout_letter(letter_paras(20), PROFILE, s, None, "letter 1", 1)
    assert len(pages) > 1
    assert not any("Page" in ln.text for ln in pages[0].lines)
    body = 66 - 12
    for page in pages[1:]:
        number = page.lines[0] if position == "top" else page.lines[-1]
        assert number.text.strip() == f"Page {page.number}" and len(number.text) == W
        if position == "bottom":
            assert len(page.lines) == body
        assert len(page.lines) <= body
    assert any(i.message == f"{len(pages)} pages" for i in issues)


def test_signature_block_stays_together():
    for n in range(14, 22):
        pages, issues = layout_letter(letter_paras(n), PROFILE, LayoutSettings())
        roles = [{ln.role for ln in p.lines} for p in pages]
        closing_pages = [i for i, r in enumerate(roles) if Role.CLOSING in r]
        assert len(closing_pages) == 1, n
        assert not any("split" in i.message for i in issues)
        last = pages[closing_pages[0]].lines
        # the closing never sits alone at the top of a page
        assert any(ln.text.startswith("The") or "river" in ln.text for ln in last), n
