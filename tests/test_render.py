import dataclasses

from daisywriter.layout import Cell, Line
from daisywriter.profile import load_profile
from daisywriter.render import encode, passes, render_line

SWINTEC = load_profile("swintec-1146cmp")
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
