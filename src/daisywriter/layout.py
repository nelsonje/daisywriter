"""Re-wrap merged paragraphs to the typewriter's line width and split them into pages.

Word's own line breaks are ignored: each paragraph is word-wrapped again at the
profile's pitch and margins. Column 0 of a Line is the typewriter's left margin.
Line 0 of a Page is the first typed line below the top margin.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import issues as I
from .model import Align, Paragraph, Role
from .profile import STOCKS, Profile

MIN_LINE_WIDTH = 10
DEFAULT_TAB_IN = 0.5


@dataclass(frozen=True)
class Cell:
    ch: str
    bold: bool = False
    underline: bool = False
    body: bool = False


BLANK = Cell(" ")


@dataclass
class Line:
    cells: list[Cell] = field(default_factory=list)
    para: int | None = None  # template paragraph index
    role: Role = Role.OTHER

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
    stock: str = "letter"
    top_lines: int = 6
    bottom_lines: int = 6
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
    def __init__(self, p: Paragraph, profile: Profile, issues: list, where: str):
        self.profile = profile
        self.issues = issues
        self.where = where
        width = profile.line_width
        left = max(0, profile.pt_to_cols(p.left_pt))
        first = max(0, left + profile.pt_to_cols(p.first_line_pt))
        self.end_col = width - max(0, profile.pt_to_cols(p.right_pt))
        if self.end_col - max(left, first) < MIN_LINE_WIDTH:
            issues.append(I.warning("indents leave almost no room for text; they're reduced", where))
            left, first = min(left, width - MIN_LINE_WIDTH), min(first, width - MIN_LINE_WIDTH)
            self.end_col = width
        self.left, self.first = left, first
        default = max(1, round(DEFAULT_TAB_IN * profile.pitch_cpi))
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
                fill = Cell(" ", underline=c.underline and cells[k + 1].underline, body=c.body)
                out += [fill] * add[gi]
                gi += 1
            out.append(c)
        return out
    return cells


def wrap_paragraph(p: Paragraph, profile: Profile, settings: LayoutSettings,
                   issues: list, where: str) -> list[tuple[Line, str]]:
    """Return (line, end) pairs; end is "page" where a forced page break follows."""
    cells = [Cell(ch, s.bold, s.underline, s.body) for s in p.spans for ch in s.text]
    if not any(c.ch.strip() for c in cells) and not any(c.ch in "\n\f" for c in cells):
        return [(Line([], p.index, p.role), "end")]
    wrapper = _Wrapper(p, profile, issues, where)
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

    @property
    def blank(self) -> bool:
        return all(not ln.cells for ln in self.lines)


def _gap_lines(points: float, profile: Profile, threshold: float) -> int:
    x = points / profile.line_pt
    n = int(x)
    return n + 1 if x - n >= threshold - 1e-9 else n


def _blocks(paragraphs: list[Paragraph], profile: Profile, settings: LayoutSettings,
            issues: list, where: str) -> list[_Block]:
    blocks: list[_Block] = []
    first_closing = next((i for i, p in enumerate(paragraphs) if p.role is Role.CLOSING), None)
    prev = None
    for i, p in enumerate(paragraphs):
        gap = 0
        same_style = prev is not None and p.style == prev.style
        if prev is not None and not (p.contextual_spacing and prev.contextual_spacing and same_style):
            gap = _gap_lines(prev.space_after_pt + p.space_before_pt, profile,
                             settings.spacing_threshold)
        # keep the signature block together, and with the end of the body
        keep = p.keep_with_next or (first_closing is not None and i + 1 < len(paragraphs)
                                    and i + 1 >= first_closing)
        lines: list[Line] = []
        first_block = True
        for line, end in wrap_paragraph(p, profile, settings, issues, f"{where}, paragraph {p.index}"):
            lines.append(line)
            if end == "page":
                blocks.append(_Block(lines, gap if first_block else 0, False,
                                     p.page_break_before and first_block, True))
                lines, first_block = [], False
        if first_block or any(ln.cells for ln in lines):  # drop the blank rest of a page break
            blocks.append(_Block(lines, gap if first_block else 0, keep,
                                 p.page_break_before and first_block))
        prev = p
    return blocks


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
        gap = b.gap if cur else 0

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


def layout_letter(paragraphs: list[Paragraph], profile: Profile, settings: LayoutSettings,
                  page_number_text: str | None = None, where: str = "",
                  letter: int | None = None) -> tuple[list[Page], list[I.Issue]]:
    issues: list[I.Issue] = []
    stock = STOCKS[settings.stock]
    page_lines = round(stock.length_in * profile.lines_per_inch)
    body_lines = page_lines - settings.top_lines - settings.bottom_lines
    pn = settings.page_numbers

    def capacity(page: int) -> int:
        return max(1, body_lines - (2 if pn.shown_on(page) else 0))

    blocks = _blocks(paragraphs, profile, settings, issues, where)
    raw_pages = paginate(blocks, capacity)

    pages = []
    for n, lines in enumerate(raw_pages, start=1):
        if pn.shown_on(n):
            num = _number_line((page_number_text or pn.format).replace("{page}", str(n)),
                               profile.line_width, pn.align)
            if pn.position == "top":
                lines = [num, Line()] + lines
            else:
                lines = lines + [Line() for _ in range(capacity(n) - len(lines))] + [Line(), num]
        pages.append(Page(n, lines))

    closing_pages = {p.number for p in pages for ln in p.lines if ln.role is Role.CLOSING}
    if len(closing_pages) > 1:
        issues.append(I.warning("the signature block is split across pages", where))
    if len(pages) > 1:
        issues.append(I.info(f"{len(pages)} pages", where))
    return pages, [I.Issue(i.level, i.message, i.where, letter) for i in issues]
