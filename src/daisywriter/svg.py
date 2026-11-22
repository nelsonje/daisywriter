"""Draw an emulated sheet as SVG, for the website's example.

The same drawing as pdf.py: every strike in Courier at 12 pt (10 characters
per inch) where the typewriter would put it, slightly transparent so
overstrikes show darker, and strikes reached from the right shifted by the
carrier play. The SVG is in points, so it's true size at 72 dpi.
"""
from __future__ import annotations

from html import escape

from .pdf import CARRIER_PLAY_IN, INK, PT
from .profile import Stock, paper_size
from .transports.emulator import STEPS_PER_INCH, UNITS_PER_INCH, Sheet

FONT = "'Courier Prime', 'Courier New', Courier, monospace"


def sheet_svg(sheet: Sheet, stock: str | Stock = "letter", top_in: float = 0.0, bottom_in: float | None = None,
              left_in: float = 0.0, right_in: float | None = None, shift_in: float = 0.0,
              play_in: float = CARRIER_PLAY_IN, title: str = "") -> str:
    """The part of the sheet from top_in to bottom_in down, and from left_in
    to right_in across, in inches from its top left corner (default: all of it)."""
    size = paper_size(stock)
    x0, y0 = left_in * PT, top_in * PT
    w = (right_in if right_in is not None else size.width_in) * PT - x0
    h = (bottom_in if bottom_in is not None else size.length_in) * PT - y0
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:g} {y0:g} {w:g} {h:g}" role="img"'
           + (f' aria-label="{escape(title)}">' if title else ">"),
           f'<rect x="{x0:g}" y="{y0:g}" width="{w:g}" height="{h:g}" fill="#fffdf7"/>',
           f'<g font-family="{FONT}" font-size="12" fill="#1b1d22" fill-opacity="{INK:g}">']
    for s in sheet.strikes:
        y = s.y / UNITS_PER_INCH * PT
        if not y0 <= y <= y0 + h + 12 or s.ch == " ":
            continue
        x = (s.x / STEPS_PER_INCH + (play_in if s.from_right else 0) - shift_in) * PT
        out.append(f'<text x="{x:.2f}" y="{y:.2f}">{escape(s.ch)}</text>')
    out.append("</g></svg>")
    return "\n".join(out)
