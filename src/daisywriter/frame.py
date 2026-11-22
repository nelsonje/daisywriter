"""Where a letter goes on the sheet: Word's page setup fitted to the typewriter.

The typewriter's margins are set on its keyboard, never from the computer, and
every power-on resets them. With the sheet against the paper guide, column c is
c / pitch inches from its left edge: the profile's margins count from there, and
its paper_guide is the guide's mark on the paper scale (on some machines the
guide is broken, and the scale is what's left). daisywriter keeps the text
inside those margins:

- A wider left margin in Word starts each line with spaces (Frame.indent).
- A narrower one starts each line with backspaces, left of the typewriter's
  margin, when the profile says the firmware allows it (left_of_margin; a
  negative Frame.indent). Otherwise the sheet goes that much right of the
  paper guide (Frame.shift_in), and the paper prompt says so.
- Word's right margin ends the lines, but never past the typewriter's right
  margin, where the typewriter would wrap the line itself.
- On single sheets the top margin is at least where the printing point is once
  a sheet is loaded (load_offset_lines).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import issues as I
from .model import PageSetup
from .profile import LETTER, Profile, Stock, guide_place, inches, paper_size, sized

MIN_WIDTH = 20  # characters per line
MIN_LINES = 6  # typed lines per page


@dataclass(frozen=True)
class Frame:
    """The text area, in the typewriter's columns and lines."""
    stock: Stock = LETTER
    indent: int = 0  # columns from the typewriter's left margin to the text
    width: int = 66  # characters per line
    top_lines: int = 6  # from the sheet's top edge to the first typed line
    bottom_lines: int = 6  # left blank at the bottom of the page
    shift_in: float = 0.0  # the sheet goes this far right of the paper guide
    margins: tuple[float, float, float, float] | None = None  # as set in Word, in inches

    @property
    def columns(self) -> int:
        """Columns from the start of the text, or the typewriter's left margin if
        that's further left, to the end of the text."""
        return max(self.indent, 0) + self.width

    def margins_in(self, profile: Profile) -> tuple[float, float, float, float]:
        """(left, right, top, bottom) in inches from the sheet's edges: Word's
        unless daisywriter had to change them, else where the text is typed."""
        if self.margins is not None:
            return self.margins
        left = (profile.margin_left + self.indent) / profile.pitch_cpi - self.shift_in
        right = self.stock.width_in - left - self.width / profile.pitch_cpi
        return (left, right, self.top_lines / profile.lines_per_inch,
                self.bottom_lines / profile.lines_per_inch)

    def describe(self, profile: Profile) -> str:
        left, right, top, bottom = (inches(x) for x in self.margins_in(profile))
        same = left if len({left, right, top, bottom}) == 1 else None
        margins = (f"margins {same} in" if same else
                   f"margins: left {left}, right {right}, top {top}, bottom {bottom} in")
        return f"{self.stock.label}, {margins}, {self.width} characters per line"


def _cols(x: float) -> int:
    return math.floor(x + 0.5)


def fit_page(page: PageSetup | None, profile: Profile, paper: str | Stock | None = None,
             top_lines: int | None = None, bottom_lines: int | None = None) -> tuple[Frame, list[I.Issue]]:
    """The frame for Word's page setup on this typewriter. paper, top_lines and
    bottom_lines override the template's. Without a page setup, the text fills
    the typewriter's margins on letter paper with 1 in top and bottom margins."""
    issues: list[I.Issue] = []
    cpi, lpi = profile.pitch_cpi, profile.lines_per_inch
    given = page
    if page is None:
        sheet = paper_size(paper) if paper else LETTER
        page = PageSetup(sheet.width_in, sheet.length_in, profile.margin_left / cpi,
                         sheet.width_in - profile.text_end / cpi, 1.0, 1.0)
    else:
        sheet = paper_size(paper) if paper else sized(page.width_in, page.length_in)

    guide = profile.margin_left / cpi  # the typewriter's left margin, from a sheet against the guide
    shift = round(guide - page.left_in, 3)
    shift = shift if shift >= 0.5 / cpi else 0.0  # less than half a column rounds away
    if profile.left_of_margin:
        shift = 0.0  # backspaces reach the text instead
    if shift:
        issues.append(I.warning(
            f"the left margin in Word ({inches(page.left_in)} in) is narrower than the "
            f"typewriter's ({inches(guide)} in): put each sheet {inches(shift)} inch to the right "
            f"of {guide_place(profile.paper_guide)}", "page setup"))
    left = _cols((page.left_in + shift) * cpi)
    end = math.floor((sheet.width_in - page.right_in + shift) * cpi + 1e-6)
    right = page.right_in
    if end > profile.text_end:
        end = profile.text_end
        right = sheet.width_in - (end / cpi - shift)
        issues.append(I.warning(
            f"the right margin in Word ({inches(page.right_in)} in) is narrower than the typewriter "
            f"allows, so lines end {inches(end / cpi - shift)} in from the sheet's left edge "
            f"(a {inches(right)} in right margin)", "page setup"))
    width = end - left
    if width < MIN_WIDTH:
        issues.append(I.error(
            f"the margins leave room for only {max(0, width)} characters per line", "page setup"))
        width = MIN_WIDTH

    top = top_lines if top_lines is not None else _cols(page.top_in * lpi)
    lowest = profile.load_offset_lines if profile.paper == "single_sheet" else 0
    if top < lowest:
        issues.append(I.warning(
            f"the top margin ({inches(top / lpi)} in) is above where the typewriter can type on a "
            f"sheet it has just loaded, so the letter starts {inches(lowest / lpi)} in down",
            "page setup"))
        top = lowest
    bottom = bottom_lines if bottom_lines is not None else max(0, _cols(page.bottom_in * lpi))
    lines = round(sheet.length_in * lpi) - top - bottom
    if lines < MIN_LINES:
        issues.append(I.error(
            f"the top and bottom margins leave room for only {max(0, lines)} lines", "page setup"))
        bottom = max(0, round(sheet.length_in * lpi) - top - MIN_LINES)

    margins = None
    if given is not None:
        margins = (page.left_in, right, top / lpi if top != _cols(page.top_in * lpi) else page.top_in,
                   bottom / lpi if bottom != _cols(page.bottom_in * lpi) else page.bottom_in)
    frame = Frame(sheet, left - profile.margin_left, width, top, bottom, shift, margins)
    return frame, issues
