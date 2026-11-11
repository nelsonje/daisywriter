import dataclasses

import pytest

from daisywriter.layout import Cell, Line
from daisywriter.profile import load_profile
from daisywriter.render import encode, passes, render_line, reverse_pass

_SW = load_profile("swintec-1146cmp")
SWINTEC = dataclasses.replace(_SW, raw={**_SW.raw, "bold_restrikes": ["left"]})
OLYMPIA = load_profile("olympia-compact-2")


def cells(text, bold=False, underline=False):
    return [Cell(ch, bold, underline) for ch in text]


def test_plain_line():
    assert render_line(Line(cells("Hello, world.")), SWINTEC) == b"Hello, world.\n"
    assert render_line(Line(), SWINTEC) == b"\n"
    assert render_line(Line(cells("  indented  ")), SWINTEC) == b"  indented\n"


def test_overstrike_bold_and_overprint_underline():
    line = Line(cells("a ") + cells("bold", bold=True) + cells(" and ") + cells("under", underline=True))
    assert render_line(line, SWINTEC) == b"a bold and under\r  bold     _____\n"
    assert passes(line, SWINTEC) == 2


def test_bold_and_underlined_needs_a_third_pass():
    line = Line(cells("x ") + cells("both it", bold=True, underline=True))
    assert render_line(line, SWINTEC) == b"x both it\r  both_it\r  ____ __\n"


def test_strikethrough_is_overtyped():
    line = Line(cells("was ") + [Cell(ch, strike=True) for ch in "$40 x"])
    assert render_line(line, SWINTEC) == b"was $40 x\r    -----\n"
    # bold and underlined and struck: re-strike, then underscores, then hyphens
    both = Line([Cell("a", bold=True, underline=True, strike=True), Cell("b", strike=True)])
    assert render_line(both, SWINTEC) == b"ab\ra-\r_\r-\n"
    assert passes(both, SWINTEC) == 4


def test_corrections_are_overtyped():
    line = Line(cells("the ") + [Cell(ch, over="x") for ch in "tje"] + cells(" the ")
                + cells("w") + [Cell("r", over="e")] + cells("b"))
    assert render_line(line, SWINTEC) == b"the tje the wrb\r    xxx      e\n"


def test_charset_mapping_and_shift_out_runs():
    assert encode("50°", OLYMPIA) == b"50>"
    # adjacent shift-out characters share one SO ... SI
    assert encode("©®", OLYMPIA) == b"\x0e-/\x0f"
    assert encode("a|b", OLYMPIA) == b"a\x0e,\x0fb"


def test_escape_code_bold_profiles():
    diablo = dataclasses.replace(SWINTEC, raw={**SWINTEC.raw, "bold": {"on": "\x1bO", "off": "\x1b&"},
                                               "underline": {"on": "\x1bE", "off": "\x1bR"}})
    line = Line(cells("a ") + cells("b", bold=True) + cells(" ") + cells("u", underline=True))
    assert render_line(line, diablo) == b"a \x1bOb\x1b& \x1bEu\x1bR\n"


def test_triple_strike_bold():
    triple = dataclasses.replace(SWINTEC, raw={**SWINTEC.raw, "bold_restrikes": ["left", "left"]})
    line = Line(cells("a ") + cells("bold", bold=True) + cells(" ") + cells("u", underline=True))
    assert render_line(line, triple) == b"a bold u\r  bold _\r  bold\n"
    both = Line(cells("x", bold=True, underline=True))
    assert render_line(both, triple) == b"x\rx\rx\r_\n"
    assert passes(both, triple) == 4


def test_bold_restrike_from_the_right():
    line = Line(cells("a ") + cells("bd", bold=True) + cells(" ") + cells("u", underline=True))
    # the re-strike runs right to left; the underscore gets a left-to-right pass of its own
    assert render_line(line, _SW) == b"a bd u\r   d\x08\x08b\r     _\n"
    assert passes(line, _SW) == 3
    both = dataclasses.replace(_SW, raw={**_SW.raw, "bold_restrikes": ["left", "right"]})
    assert render_line(line, both) == b"a bd u\r  bd _\r   d\x08\x08b\n"


def test_unknown_restrike_direction():
    bad = dataclasses.replace(_SW, raw={**_SW.raw, "bold_restrikes": ["up"]})
    with pytest.raises(ValueError, match="bold_restrikes"):
        render_line(Line(cells("x", bold=True)), bad)


def test_reverse_pass_reaches_each_letter_from_the_right():
    # "ab cd" from column 2: d at 6, then back over c, the space, b, a
    assert reverse_pass(cells("  ab cd"), SWINTEC) == b"      d\x08\x08c\x08\x08\x08b\x08\x08a"
    assert reverse_pass(cells("    "), SWINTEC) == b""


def test_raw_lines_are_typed_as_is():
    line = Line(cells("ignored"), raw=b"ab\rab")
    assert render_line(line, SWINTEC) == b"ab\rab\n"
    assert passes(line, SWINTEC) == 2


def test_bold_test_page():
    from daisywriter.testpage import bold_page
    page = bold_page(SWINTEC)
    rows = {line.text.split(":")[0]: line for line in page.lines if line.raw is not None}
    assert passes(rows["plain"], SWINTEC) == 1
    assert passes(rows["3, left+right"], SWINTEC) == 3
    assert b"\x08" in rows["2, right"].raw and b"\x08" not in rows["3, left"].raw
    assert all(len(line.text) <= SWINTEC.line_width for line in page.lines)
