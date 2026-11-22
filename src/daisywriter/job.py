"""Send letters to a typewriter, a line at a time.

Lines go a byte at a time. The typewriter takes the next line only once it has
typed the last one, and the adapter holds just a few bytes (`daisywriter
probe`, 2026-11-19), so a write waits while the line before is typed. Checking
for Stop between bytes means Stop takes effect when the line being typed is
done: the bytes of the next one are still in the typewriter's line buffer,
with no newline to type them, and the CAN sent after stopping discards them.
Sending whole lines, Stop came two lines late. The timeout applies per byte,
so it covers one line's typing. Before each page the job checks the port
status, and with single sheets it waits for paper.
"""
from __future__ import annotations

import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass

from .frame import Frame
from .layout import Page
from .merge import Letter
from .profile import LETTER, Profile, Stock, guide_place, inches
from .render import CAN, FF, newline, passes, render_line
from .transports import Transport, TransportError

# ask(message) -> True to go on, False to cancel. Used for paper prompts and retries.
Ask = Callable[[str], bool]
Report = Callable[[str], None]
Stop = Callable[[], bool]  # checked between bytes; True cancels the job
# progress(letter number, page number, lines sent, lines on the page)
Progress = Callable[[int, int, int, int], None]


def _never() -> bool:
    return False


def _ignore(*args) -> None:
    pass


class PrintCancelled(Exception):
    pass


@dataclass
class PrintOptions:
    paper: str = "single_sheet"  # or "continuous"
    stock: Stock = LETTER
    top_lines: int = 6  # top margin: lines from the sheet's top edge to the first line
    shift_in: float = 0.0  # single sheets go this far right of the paper guide
    paper_guide: int | None = None  # its mark on the paper scale, for the prompts
    eject: bool = True  # single sheets: feed to the end of the page afterwards
    line_pause_s: float = 0.0  # pause after each line (to lower the average power draw)
    timeout_s: float = 60.0  # per line

    @classmethod
    def for_profile(cls, profile: Profile, frame: Frame | None = None, **kw) -> PrintOptions:
        """Options from the profile, the letters' paper and margins, then kw."""
        base = cls(paper=profile.paper, line_pause_s=float(profile.raw.get("line_pause_s", 0.0)),
                   paper_guide=profile.paper_guide)
        if frame is not None:
            base.stock, base.top_lines, base.shift_in = frame.stock, frame.top_lines, frame.shift_in
        for k, v in kw.items():
            if v is not None:
                setattr(base, k, v)
        return base


def sheet_prompt(opts: PrintOptions, where: str) -> str:
    sheet = "a sheet" if opts.stock == LETTER else f"a sheet of {opts.stock.label} paper"
    if opts.shift_in:
        place = (f" Put its left edge {inches(opts.shift_in)} inch to the right of "
                 f"{guide_place(opts.paper_guide)}.")
    else:
        place = f" Put its left edge against {guide_place(opts.paper_guide, 'at')}."
    return (f"Insert {sheet} for {where} until the rollers above the printing point catch it."
            f"{place} Then continue?")


def wait_ready(transport: Transport, ask: Ask):
    while True:
        st = transport.status()
        if st is None or st.ready:
            return
        if not ask(f"Typewriter not ready: {st.explain()}. Retry?"):
            raise PrintCancelled()


def print_page(transport: Transport, page: Page, profile: Profile, opts: PrintOptions,
               report: Report = _ignore, label: str = "", stop: Stop = _never,
               progress: Callable[[int, int], None] = _ignore):
    nl = newline(profile)
    page_lines = round(opts.stock.length_in * profile.lines_per_inch)
    # a loaded sheet already sits load_offset_lines below its top edge (single sheets)
    loaded = profile.load_offset_lines if opts.paper == "single_sheet" else 0
    if opts.top_lines > loaded:
        transport.write(nl * (opts.top_lines - loaded), opts.timeout_s)
    t0 = time.monotonic()
    for n, line in enumerate(page.lines, start=1):
        for b in render_line(line, profile):
            if stop():
                raise PrintCancelled()
            transport.write(bytes([b]), opts.timeout_s)
        progress(n, len(page.lines))
        extra = f" ({passes(line, profile)} passes)" if passes(line, profile) > 1 else ""
        report(f"{label}line {n}/{len(page.lines)} sent at {time.monotonic() - t0:5.1f} s{extra}")
        if opts.line_pause_s and line.cells:
            time.sleep(opts.line_pause_s)
    if opts.paper == "continuous":
        transport.write(FF, opts.timeout_s)
    elif opts.eject:
        at = max(opts.top_lines, loaded) + len(page.lines)  # lines below the top edge
        rest = page_lines - at + profile.eject_extra_lines
        if rest > 0:
            transport.write(nl * rest, opts.timeout_s)


def print_letters(transport: Transport, letters: list[Letter], profile: Profile,
                  opts: PrintOptions, ask: Ask, report: Report = print, stop: Stop = _never,
                  progress: Progress = _ignore) -> list[int]:
    """Print letters in order; returns the numbers of the letters printed in full."""
    done = []
    try:
        for letter in letters:
            for page in letter.pages:
                where = f"letter {letter.number}, page {page.number} of {len(letter.pages)}"
                if opts.paper == "single_sheet" and not ask(sheet_prompt(opts, where)):
                    raise PrintCancelled()
                if opts.paper == "single_sheet" and hasattr(transport, "load_sheet"):
                    transport.load_sheet()  # the emulator needs to know
                wait_ready(transport, ask)
                report(f"typing {where}")
                print_page(transport, page, profile, opts, report, "  ", stop,
                           lambda n, total, ln=letter.number, pn=page.number: progress(ln, pn, n, total))
            done.append(letter.number)
    except (PrintCancelled, KeyboardInterrupt, TransportError):
        cancel(transport)
        raise
    return done


def cancel(transport: Transport):
    """Discard text the typewriter has buffered but not printed yet."""
    with contextlib.suppress(TransportError, OSError):  # the connection may already be gone
        transport.write(CAN, 2.0)
