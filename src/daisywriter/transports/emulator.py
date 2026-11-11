"""A model of the Nakajima printer firmware (Olympia Compact 2, Swintec 1146 CMP)
that types onto virtual sheets, so the bytes daisywriter sends can be checked
without a typewriter.

It follows FIRMWARE_NOTES.md (in the olympia-compact-electronic-2 repo) and the
measurements in docs/PLAN.md §16:
- Text goes into a line buffer (a column image) and is typed, left to right,
  when CR, LF, FF, BS, BEL, ESC, SO or SI arrives. CAN discards it.
- CR sets the next column to the left margin, LF also does that and feeds a
  line, and neither moves the carrier: it travels when the next text is typed.
- BS moves the next column back one. ESC takes the next printable byte as its
  argument (P/E/F/M pitch, 6/4/3 lpi, U/D platen 1/12 in); control codes in
  between still run.
- A character past the right-margin column makes the firmware type the line,
  feed, and continue at the left margin (auto-wrap). daisywriter must never
  trigger it.
- Single sheets are loaded with the printing point load_offset_lines below the
  top edge (the rollers above the printing point have just caught the sheet),
  so the sheet comes out once its bottom edge is that far above the printing
  point.

What isn't known is reported rather than guessed: spaces buffered right
before BS, ESC, SO or SI may be dropped by the firmware.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..profile import STOCKS, Profile
from .base import PortStatus

STEPS_PER_INCH = 60  # carrier: one step is 1/60 in
UNITS_PER_INCH = 12  # platen: one unit is 1/12 in
PITCH_STEPS = {ord("P"): 6, ord("E"): 5, ord("F"): 5, ord("M"): 4}  # Olympia ESC E, Swintec ESC F
LPI_UNITS = {ord("6"): 2, ord("4"): 3, ord("3"): 4}
SO, SI, ESC = 0x0E, 0x0F, 0x1B
UNSURE = {"BS", "ESC", "SO", "SI", "BEL"}


@dataclass(frozen=True)
class Strike:
    x: int  # carrier position, 1/60 in from the left stop
    y: int  # printing point, 1/12 in below the sheet's top edge
    ch: str
    from_right: bool  # the carrier reached it moving left


@dataclass
class Sheet:
    number: int
    length: int  # 1/12 in
    strikes: list[Strike] = field(default_factory=list)
    out: bool = False  # fed out past the rollers

    def grid(self, steps: int = 6, units: int = 2) -> dict[tuple[int, int], list[str]]:
        """Characters struck at each (line, column) of a pitch/line-spacing grid."""
        g: dict[tuple[int, int], list[str]] = {}
        for s in self.strikes:
            g.setdefault((s.y // units, s.x // steps), []).append(s.ch)
        return g


class Emulator:
    """A transport that types onto Sheets. events lists anything a real
    typewriter would get wrong or that the model can't be sure of."""

    def __init__(self, profile: Profile, paper: str | None = None, stock: str = "letter"):
        self.name = f"emulated {profile.name}"
        self.profile = profile
        self.paper = paper or profile.paper
        self.length = round(STOCKS[stock].length_in * UNITS_PER_INCH)
        self.unit_line = UNITS_PER_INCH // profile.lines_per_inch
        self.rollers = profile.load_offset_lines * self.unit_line  # above the printing point
        self.steps = round(STEPS_PER_INCH / profile.pitch_cpi)
        self.left, self.right = profile.margin_left, profile.margin_right
        self.col = self.carrier = self.left  # next column for text; the carrier's column
        self.buf: dict[int, int] = {}  # column -> byte, not typed yet
        self.shift = self.esc = False
        self.counter = self.length  # top-of-form line counter, set when going on-line
        self.y = 0
        self.sheets: list[Sheet] = []
        self.events: list[str] = []
        self._glyphs = _glyph_table(profile)
        if self.paper == "continuous":
            self._new_sheet(0)

    # Transport interface

    def status(self) -> PortStatus:
        return PortStatus.from_byte(0x18)  # always ready

    def write(self, data: bytes, timeout_s: float = 0) -> None:
        for b in data:
            self._byte(b)

    def close(self) -> None:
        if any(b != 0x20 for b in self.buf.values()):
            self._event("text was left in the typewriter's buffer, never typed (no CR or LF after it)")

    def load_sheet(self) -> None:
        """The user inserted a sheet until the rollers caught it (single sheets)."""
        if self.paper == "continuous":
            return
        if self.sheets and not self.sheets[-1].out:
            self._event(f"sheet {self.sheets[-1].number} was still held by the rollers "
                        "when the next sheet was loaded")
        self._new_sheet(self.rollers)

    # The firmware

    @property
    def sheet(self) -> Sheet | None:
        return self.sheets[-1] if self.sheets else None

    def _new_sheet(self, y: int):
        self.sheets.append(Sheet(len(self.sheets) + 1, self.length))
        self.y = y

    def _event(self, message: str):
        where = f"sheet {self.sheet.number}, line {self.y / self.unit_line + 1:g}: " if self.sheet else ""
        self.events.append(where + message)

    def _byte(self, b: int):
        if b == 0x0D:
            self._flush("CR")
            self.col = self.left
        elif b == 0x0A:
            self._flush("LF")
            self._feed(self.unit_line)
            self.col = self.left
        elif b == 0x0C:
            self._flush("FF")
            self._feed(self.counter)
            self.col = self.left
        elif b == 0x08:
            self._flush("BS")
            self.col = max(0, self.col - 1)
        elif b == 0x07:
            self._flush("BEL")
        elif b in (SO, SI):
            self._flush("SO" if b == SO else "SI")
            self.shift = b == SO
        elif b == 0x18:
            self.buf.clear()
        elif b == ESC:
            self.esc = True
        elif 0x20 <= b < 0x7F:
            if self.esc:
                self.esc = False
                self._flush("ESC")
                self._escape(b)
                return
            if self.col > self.right:
                self._event(f"the firmware wrapped the line at column {self.col} (past the right margin)")
                self._flush("wrap")
                self._feed(self.unit_line)
                self.col = self.left
            self.buf[self.col] = b
            self.col += 1
        # HT, DC1, other control codes, DEL and bytes 80-FF: ignored or dropped

    def _escape(self, b: int):
        if b in PITCH_STEPS:
            new = PITCH_STEPS[b]
            scale = lambda c: (c * self.steps * 2 + new) // (new * 2)  # round half up
            self.left, self.right, self.col, self.carrier = map(
                scale, (self.left, self.right, self.col, self.carrier))
            self.steps = new
        elif b in LPI_UNITS:
            self.unit_line = LPI_UNITS[b]
        elif b == ord("U"):
            self._feed(1)
        elif b == ord("D"):
            self._feed(-1)

    def _flush(self, why: str):
        typed = sorted(c for c, b in self.buf.items() if b != 0x20)
        if self.buf and why in UNSURE and (not typed or max(self.buf) > typed[-1]):
            self._event(f"spaces just before {why} at column {max(self.buf)}: "
                        "the firmware may drop them (unverified)")
        for c in typed:
            self._strike(c, self._glyph(self.buf[c]))
        self.buf.clear()

    def _glyph(self, b: int) -> str:
        ch = self._glyphs.get((self.shift, b))
        if ch is None:
            ch = "?" if self.shift or chr(b) in self.profile.unavailable else chr(b)
            if ch == "?":
                self._event(f"byte {b:#04x}{' under SO' if self.shift else ''} types a character "
                            "the profile doesn't describe")
        return ch

    def _strike(self, col: int, ch: str):
        sheet = self.sheet
        if sheet is None or sheet.out:
            self._event(f"typed {ch!r} with no sheet in the typewriter")
            return
        if self.y > sheet.length:
            self._event(f"typed {ch!r} below the bottom edge of the sheet")
        sheet.strikes.append(Strike(col * self.steps, self.y, ch, col < self.carrier))
        self.carrier = col + 1

    def _feed(self, units: int):
        self.y += units
        self.counter -= units
        while self.counter <= 0:
            self.counter += self.length
        sheet = self.sheet
        if self.paper == "continuous":
            while self.y >= self.length:
                self._new_sheet(self.y - self.length)
        elif sheet and not sheet.out and self.y > sheet.length + self.rollers:
            sheet.out = True


def _glyph_table(profile: Profile) -> dict[tuple[bool, int], str]:
    """(shifted, byte) -> the character the profile says it types."""
    table = {}
    for ch, seq in profile.charset.items():
        shifted = seq[:1] == bytes([SO])
        body = seq[1:-1] if shifted else seq
        if len(body) == 1:
            table[(shifted, body[0])] = ch
    return table


def emulate(letters, profile: Profile, opts=None) -> Emulator:
    """Type letters onto an emulator, answering every paper prompt with yes."""
    from ..job import PrintOptions, print_letters
    e = Emulator(profile, opts.paper if opts else None, opts.stock if opts else "letter")
    print_letters(e, letters, profile, opts or PrintOptions.for_profile(profile),
                  lambda message: True, lambda s: None)
    e.close()
    return e
