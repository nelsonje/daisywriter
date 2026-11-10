"""Show laid-out letters as text (plain or ANSI) or HTML.

The frame is drawn at the typewriter's margins: column 0 is the left margin
and the right edge is the last column text may use. Lines in the letter body
(where typing errors are allowed) are marked in the gutter.
"""
from __future__ import annotations

import html

from .layout import Cell, Line
from .merge import Letter

BODY_MARK = "┃"


def _heading(letter: Letter, total: int, page: int, pages: int) -> str:
    who = letter.summary()
    who = f" · {who}" if who else ""
    return f"Letter {letter.number} of {total} · row {letter.record.row}{who} · page {page} of {pages}"


STRIKE = "\u0336"  # combining long stroke overlay


def _plain_line(cells: list[Cell], width: int) -> list[str]:
    text = "".join(c.ch + (STRIKE if c.strike else "") for c in cells) + " " * max(0, width - len(cells))
    out = [text]
    if any(c.underline for c in cells):
        out.append("".join("‾" if c.underline else " " for c in cells).ljust(width))
    return out


def _ansi_line(cells: list[Cell], width: int) -> str:
    out, state = [], (False, False, False)
    for c in cells:
        s = (c.bold, c.underline, c.strike)
        if s != state:
            out.append("\x1b[0m" + ("\x1b[1m" if c.bold else "") + ("\x1b[4m" if c.underline else "")
                       + ("\x1b[9m" if c.strike else ""))
            state = s
        out.append(c.ch)
    if state != (False, False, False):
        out.append("\x1b[0m")
    return "".join(out) + " " * max(0, width - len(cells))


def _is_body(line: Line) -> bool:
    return any(c.body for c in line.cells)


def render_text(letters: list[Letter], total: int, width: int, ansi: bool = False) -> str:
    out = []
    for letter in letters:
        for page in letter.pages:
            out.append(_heading(letter, total, page.number, len(letter.pages)))
            out.append("  ┌" + "─" * width + "┐")
            for line in page.lines:
                mark = BODY_MARK if _is_body(line) else " "
                if ansi:
                    mark = f"\x1b[36m{mark}\x1b[0m" if mark != " " else mark
                    out.append(f"{mark} │{_ansi_line(line.cells, width)}│")
                else:
                    rows = _plain_line(line.cells, width)
                    out.append(f"{mark} │{rows[0]}│")
                    out += [f"  │{r}│" for r in rows[1:]]
            out.append("  └" + "─" * width + "┘")
            out.append("")
    return "\n".join(out)


HTML_STYLE = """
body { font-family: system-ui, sans-serif; background: #eee; margin: 2em; }
h2 { font-size: 1em; font-weight: 600; margin: 1.5em 0 .4em; }
.page { background: white; display: inline-block; padding: 1em 1.5em; box-shadow: 0 1px 4px #0003; }
pre { margin: 0; font: 15px/1.25 "Courier New", Courier, monospace; }
.line { display: block; white-space: pre; }
.body { background: #fff7d6; }
.edge { border-right: 1px dashed #bbb; display: inline-block; }
b { font-weight: 900; }
"""


def _html_cells(cells: list[Cell]) -> str:
    out = []
    for c in cells:
        ch = html.escape(c.ch)
        if c.strike:
            ch = f"<s>{ch}</s>"
        if c.underline:
            ch = f"<u>{ch}</u>"
        if c.bold:
            ch = f"<b>{ch}</b>"
        out.append(ch)
    return "".join(out).replace("</s><s>", "").replace("</u><u>", "").replace("</b><b>", "")


def render_html(letters: list[Letter], total: int, width: int, title: str = "daisywriter preview") -> str:
    parts = [f"<!doctype html><meta charset='utf-8'><title>{html.escape(title)}</title>",
             f"<style>{HTML_STYLE}</style>",
             ("<p>Shaded lines are the letter body, where typing errors may be added. "
              "The dashed edge is the right margin.</p>")]
    for letter in letters:
        for page in letter.pages:
            parts.append(f"<h2>{html.escape(_heading(letter, total, page.number, len(letter.pages)))}</h2>")
            parts.append("<div class='page'><pre>")
            for line in page.lines:
                cls = "line body" if _is_body(line) else "line"
                content = _html_cells(line.cells) + " " * max(0, width - len(line.cells))
                parts.append(f"<span class='{cls}'><span class='edge'>{content}</span></span>")
            parts.append("</pre></div>")
    return "\n".join(parts)
