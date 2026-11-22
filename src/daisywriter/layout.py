"""Re-wrap merged paragraphs to the typewriter's line width and split them into pages.

Word's own line breaks are ignored: each paragraph is word-wrapped again at the
profile's pitch and the margins in the template's page setup (frame.py).
Column 0 of a Line is the typewriter's left margin, so lines start with
frame.indent blank cells (or start left of the margin when it's negative). Line 0 of a Page is the first typed line below the
top margin.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import issues as I
from .frame import Frame, fit_page
from .model import Align, Paragraph, Role
from .profile import Profile

MIN_LINE_WIDTH = 10


@dataclass(frozen=True)
class Cell:
    ch: str
    bold: bool = False
    underline: bool = False
    body: bool = False
    strike: bool = False
    over: str = ""  # characters struck over this one (typing-error corrections)


BLANK = Cell(" ")


@dataclass
class Line:
    cells: list[Cell] = field(default_factory=list)
    para: int | None = None  # template paragraph index
    role: Role = Role.OTHER
    raw: bytes | None = None  # typed as is instead of rendering the cells (calibration pages)
    outdent: int = 0  # the first cell is this many columns left of the typewriter's left margin

    @property
    def text(self) -> str:
        return "".join(c.ch for c in self.cells)


@dataclass
class Page:
    number: int
    lines: list[Line]


@dataclass
class PageNumbers:
    mode: str = "off"  # "off" | "after_first" | "all"
    position: str = "top"  # "top" | "bottom"
    align: str = "center"  # "left" | "center" | "right"
    format: str = "- {page} -"  # may contain merge placeholders such as {{LastName}}

    def shown_on(self, page: int) -> bool:
        return self.mode == "all" or (self.mode == "after_first" and page > 1)


@dataclass
class LayoutSettings:
    # None: from the template's page setup (Word's Layout > Size and Margins)
    stock: str | None = None  # letter, legal, a4 or WIDTHxLENGTH in inches
    top_lines: int | None = None
    bottom_lines: int | None = None
    justify: bool = True  # False types justified paragraphs ragged-right
    spacing_threshold: float = 0.5  # fraction of a line at which Word spacing becomes a blank line
    page_numbers: PageNumbers = field(default_factory=PageNumbers)


# ---------------------------------------------------------------- wrapping

@dataclass
class _Wrapped:
    cells: list[Cell]
    end: str  # "wrap" | "break" | "end" | "page"
    fixed: int  # cells before this index aren't stretched by justification
    start: int  # indent of this line


def _tokens(cells: list[Cell]):
    word: list[Cell] = []
    for c in cells:
        if c.ch in " \t\n\f":
            if word:
                yield "word", word
                word = []
            yield {" ": "space", "\t": "tab", "\n": "break", "\f": "page"}[c.ch], c
        else:
            word.append(c)
    if word:
        yield "word", word


class _Wrapper:
    def __init__(self, p: Paragraph, profile: Profile, issues: list, where: str, width: int):
        self.profile = profile
        self.issues = issues
        self.where = where
        left = max(0, profile.pt_to_cols(p.left_pt))
        first = max(0, left + profile.pt_to_cols(p.first_line_pt))
        self.end_col = width - max(0, profile.pt_to_cols(p.right_pt))
        if self.end_col - max(left, first) < MIN_LINE_WIDTH:
            issues.append(I.warning("indents leave almost no room for text; they're reduced", where))
            left, first = min(left, width - MIN_LINE_WIDTH), min(first, width - MIN_LINE_WIDTH)
            self.end_col = width
        self.left, self.first = left, first
        default = max(1, profile.pt_to_cols(p.default_tab_pt))
        stops = {profile.pt_to_cols(t) for t in p.tab_stops_pt}
        if p.first_line_pt < 0:
            stops.add(left)  # a hanging indent acts as a tab stop, as in Word
        self.stops = sorted(stops)
        self.default_tab = default
        self.out: list[_Wrapped] = []
        self._new_line(first)

    def _new_line(self, start):
        self.cur = [BLANK] * start
        self.start = start
        self.fixed = start
        self.has_text = False
        self.pending: list[Cell] = []

    def _finish(self, end):
        cells = self.cur
        while len(cells) > self.start and cells[-1].ch == " ":
            cells = cells[:-1]
        self.out.append(_Wrapped(cells, end, self.fixed, self.start))
        self._new_line(self.left)

    @property
    def col(self):
        return len(self.cur)

    def _next_tab(self, col):
        for s in self.stops:
            if s > col:
                return s
        return (col // self.default_tab + 1) * self.default_tab

    def tab(self):
        target = self._next_tab(self.col + len(self.pending))
        if target >= self.end_col:
            self._finish("wrap")
            target = self._next_tab(self.col)
            if target >= self.end_col:
                target = self.col
        self.cur += [BLANK] * (target - self.col)
        self.pending = []
        self.fixed = len(self.cur)
        self.has_text = True

    def word(self, w: list[Cell]):
        need = len(self.pending) + len(w)
        if self.col + need <= self.end_col:
            self.cur += self.pending + w
        else:
            if self.has_text:
                # break after a hyphen inside the word if the first part fits
                room = self.end_col - self.col - len(self.pending)
                cut = max((k for k in range(min(room, len(w) - 1)) if w[k].ch == "-"), default=None)
                if cut is not None:
                    self.cur += self.pending + w[:cut + 1]
                    w = w[cut + 1:]
                self._finish("wrap")
            while self.col + len(w) > self.end_col:
                room = self.end_col - self.col
                self.issues.append(I.error(
                    f"\"{''.join(c.ch for c in w)}\" is longer than the line ({room} columns) "
                    "and is split", self.where))
                self.cur += w[:room]
                w = w[room:]
                self._finish("wrap")
            self.cur += w
        self.pending = []
        self.has_text = True

    def run(self, cells: list[Cell]) -> list[_Wrapped]:
        for kind, tok in _tokens(cells):
            if kind == "space":
                if self.has_text:
                    self.pending.append(tok)
            elif kind == "tab":
                self.tab()
            elif kind == "break":
                self._finish("break")
            elif kind == "page":
                self._finish("page")
            else:
                self.word(tok)
        self._finish("end")
        return self.out


def _align(w: _Wrapped, align: Align, end_col: int, justify: bool, flip: bool) -> list[Cell]:
    cells = w.cells
    used = len(cells)
    extra = end_col - used
    if extra <= 0 or used <= w.start:
        return cells
    if align is Align.CENTER:
        return cells[:w.start] + [BLANK] * (extra // 2) + cells[w.start:]
    if align is Align.RIGHT:
        return cells[:w.start] + [BLANK] * extra + cells[w.start:]
    if align is Align.JUSTIFY and justify and w.end == "wrap":
        gaps = [k for k in range(max(w.fixed, w.start) + 1, used)
                if cells[k].ch == " " and cells[k - 1].ch != " "]
        if not gaps:
            return cells
        add = [extra // len(gaps)] * len(gaps)
        order = range(len(gaps) - 1, -1, -1) if flip else range(len(gaps))
        for n, g in enumerate(order):
            if n < extra % len(gaps):
                add[g] += 1
        out, gi = [], 0
        for k, c in enumerate(cells):
            if gi < len(gaps) and k == gaps[gi]:
                fill = Cell(" ", underline=c.underline and cells[k + 1].underline, body=c.body,
                            strike=c.strike and cells[k + 1].strike)
                out += [fill] * add[gi]
                gi += 1
            out.append(c)
        return out
    return cells


def wrap_paragraph(p: Paragraph, profile: Profile, settings: LayoutSettings,
                   issues: list, where: str, width: int | None = None) -> list[tuple[Line, str]]:
    """Return (line, end) pairs; end is "page" where a forced page break follows.
    width: characters per line (default: the typewriter's margins)."""
    cells = [Cell(ch, s.bold, s.underline, s.body, s.strike, s.over) for s in p.spans for ch in s.text]
    if _is_empty(p):
        return [(Line([], p.index, p.role), "end")]
    wrapper = _Wrapper(p, profile, issues, where, width or profile.line_width)
    wrapped = wrapper.run(cells)
    out = []
    for n, w in enumerate(wrapped):
        cells = _align(w, p.align, wrapper.end_col, settings.justify, flip=n % 2 == 1)
        out.append((Line(cells, p.index, p.role), w.end))
    return out


# ---------------------------------------------------------------- pagination

@dataclass
class _Block:
    lines: list[Line]
    gap: int  # blank lines before the block
    keep_with_next: bool = False
    break_before: bool = False
    page_after: bool = False
    top_gap: int = 0  # blank lines kept when the block starts the first page or follows a page break

    @property
    def blank(self) -> bool:
        return all(not ln.cells for ln in self.lines)


def _gap_lines(points: float, profile: Profile, threshold: float) -> int:
    x = points / profile.line_pt
    n = int(x)
    return n + 1 if x - n >= threshold - 1e-9 else n


def _blocks(paragraphs: list[Paragraph], profile: Profile, settings: LayoutSettings,
            issues: list, where: str, width: int) -> list[_Block]:
    """Wrap paragraphs into blocks of lines.

    Empty paragraphs don't become blocks: their height joins Word's space
    before/after in one total, which is rounded to whole blank lines once, so
    rounding doesn't add up across a run of empty paragraphs.
    """
    blocks: list[_Block] = []
    nonempty = [i for i, p in enumerate(paragraphs) if not _is_empty(p)]
    first_closing = next((i for i in nonempty if paragraphs[i].role is Role.CLOSING), None)
    # keep the signature block together, and with the end of the body
    chain_from = max((i for i in nonempty if first_closing is not None and i < first_closing),
                     default=first_closing)
    last = nonempty[-1] if nonempty else None
    space_pt, empties = 0.0, 0
    prev = None
    for i, p in enumerate(paragraphs):
        same_style = prev is not None and p.style == prev.style
        if prev is not None and not (p.contextual_spacing and prev.contextual_spacing and same_style):
            space_pt += prev.space_after_pt + p.space_before_pt
        prev = p
        if _is_empty(p):
            space_pt += profile.line_pt
            empties += 1
            continue
        gap = _gap_lines(space_pt, profile, settings.spacing_threshold)
        top_gap = empties
        space_pt, empties = 0.0, 0
        keep = p.keep_with_next or (chain_from is not None and chain_from <= i < last)
        lines: list[Line] = []
        first_block = True
        for line, end in wrap_paragraph(p, profile, settings, issues, f"{where}, paragraph {p.index}", width):
            lines.append(line)
            if end == "page":
                blocks.append(_Block(lines, gap if first_block else 0, False,
                                     p.page_break_before and first_block, True,
                                     top_gap if first_block else 0))
                lines, first_block = [], False
        if first_block or any(ln.cells for ln in lines):  # drop the blank rest of a page break
            blocks.append(_Block(lines, gap if first_block else 0, keep,
                                 p.page_break_before and first_block, False,
                                 top_gap if first_block else 0))
    return blocks


def _is_empty(p: Paragraph) -> bool:
    """A paragraph with no text: in Word, one blank line."""
    return not any(ch.strip() or ch in "\n\f" for s in p.spans for ch in s.text)


def paginate(blocks: list[_Block], capacity) -> list[list[Line]]:
    pages: list[list[Line]] = [[]]
    overflow = False  # the current page was started because the previous one filled up

    def new_page(by_overflow: bool):
        nonlocal overflow
        pages.append([])
        overflow = by_overflow

    def room() -> int:
        return capacity(len(pages)) - len(pages[-1])

    queue = list(blocks)
    i = 0
    while i < len(queue):
        b = queue[i]
        cur = pages[-1]
        if b.break_before and cur:
            new_page(False)
            continue
        if not cur and overflow and b.blank:
            i += 1  # no blank lines at the top of a continuation page
            continue
        # Word's spacing disappears at the top of a page; empty paragraphs only do so on
        # pages that start because the previous one filled up
        gap = b.gap if cur else (0 if overflow else b.top_gap)

        # a keep-with-next chain moves to a new page as a unit when it fits there
        j = i
        while queue[j].keep_with_next and j + 1 < len(queue) and not queue[j + 1].break_before:
            j += 1
        if j > i and cur:
            # the first block may still split, leaving its last 2 lines with the chain
            first = min(2, len(b.lines)) if len(b.lines) >= 4 else len(b.lines)
            need = gap + first + sum(len(x.lines) + x.gap for x in queue[i + 1:j])
            need += queue[j].gap + min(2, len(queue[j].lines))
            if need > room() and need <= capacity(len(pages) + 1):
                new_page(True)
                continue

        avail = room() - gap
        n = len(b.lines)
        if n <= avail:
            cur += [Line() for _ in range(gap)] + b.lines
            i += 1
            if b.page_after:
                new_page(False)
            continue
        if not cur:
            k = max(1, avail)  # the block is taller than a page
        elif n >= 4 and avail >= 2:
            k = min(avail, n - 2)  # leave no single line at the bottom or the top
            k = k if k >= 2 else 0
        else:
            k = 0
        if k:
            cur += [Line() for _ in range(gap)] + b.lines[:k]
            queue[i] = _Block(b.lines[k:], 0, b.keep_with_next, False, b.page_after)
        new_page(True)

    while len(pages) > 1 and not pages[-1]:
        pages.pop()
    return pages


def _number_line(text: str, width: int, align: str) -> Line:
    text = text[:width]
    pad = {"left": 0, "center": (width - len(text)) // 2, "right": width - len(text)}[align]
    return Line([BLANK] * pad + [Cell(ch) for ch in text])


def _indented(line: Line, indent: int) -> Line:
    """The line moved right of the left margin (indent > 0) or left of it."""
    if not line.cells:
        return line
    if indent < 0:
        return Line(line.cells, line.para, line.role, line.raw, -indent)
    return Line([BLANK] * indent + line.cells, line.para, line.role, line.raw)


def layout_letter(paragraphs: list[Paragraph], profile: Profile, settings: LayoutSettings,
                  page_number_text: str | None = None, where: str = "",
                  letter: int | None = None, frame: Frame | None = None) -> tuple[list[Page], list[I.Issue]]:
    """frame: where the text goes (default: the typewriter's margins on letter paper,
    or the paper and margins in settings)."""
    issues: list[I.Issue] = []
    if frame is None:
        frame, _ = fit_page(None, profile, settings.stock, settings.top_lines, settings.bottom_lines)
    page_lines = round(frame.stock.length_in * profile.lines_per_inch)
    body_lines = page_lines - frame.top_lines - frame.bottom_lines
    pn = settings.page_numbers

    def capacity(page: int) -> int:
        return max(1, body_lines - (2 if pn.shown_on(page) else 0))

    blocks = _blocks(paragraphs, profile, settings, issues, where, frame.width)
    raw_pages = paginate(blocks, capacity)

    pages = []
    for n, lines in enumerate(raw_pages, start=1):
        if pn.shown_on(n):
            num = _number_line((page_number_text or pn.format).replace("{page}", str(n)),
                               frame.width, pn.align)
            if pn.position == "top":
                lines = [num, Line()] + lines
            else:
                lines = lines + [Line() for _ in range(capacity(n) - len(lines))] + [Line(), num]
        if frame.indent:
            lines = [_indented(ln, frame.indent) for ln in lines]
        pages.append(Page(n, lines))

    closing_pages = {p.number for p in pages for ln in p.lines if ln.role is Role.CLOSING}
    if len(closing_pages) > 1:
        issues.append(I.warning("the signature block is split across pages", where))
    if len(pages) > 1:
        issues.append(I.info(f"{len(pages)} pages", where))
    return pages, [I.Issue(i.level, i.message, i.where, letter) for i in issues]
