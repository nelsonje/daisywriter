"""Turn laid-out lines into the bytes a typewriter needs.

Typewriters without bold or underline codes (the Nakajima machines) get them by
typing a line in passes: the text, then CR and passes with bold re-strikes,
underscores and strikethrough marks. Each cell takes its marks in that order,
one per pass, so a pass holds the first mark of every cell, the next pass the
second, and so on. CR returns to the left margin without feeding, and leading
spaces become carrier moves, so extra passes cost one carriage return each.
"""
from __future__ import annotations

from .layout import Cell, Line
from .profile import Profile

SO, SI = b"\x0e", b"\x0f"
BS, CR, FF, CAN = b"\x08", b"\r", b"\x0c", b"\x18"


def encode(text: str, profile: Profile) -> bytes:
    out = bytearray()
    for ch in text:
        mapped = profile.charset.get(ch)
        if mapped is not None:
            out += mapped
        else:
            out += ch.encode("ascii")  # validation guarantees typeable characters
    return bytes(out).replace(SI + SO, b"")  # merge adjacent shift-out runs


def newline(profile: Profile) -> bytes:
    return profile.raw.get("newline", "\n").encode("latin-1")


def _codes(profile: Profile, attr: str):
    """(on, off) bytes when the profile has escape codes for bold/underline, else None."""
    spec = profile.raw.get(attr)
    if isinstance(spec, dict):
        return spec["on"].encode("latin-1"), spec["off"].encode("latin-1")
    return None


def _overprint_passes(cells: list[Cell], profile: Profile) -> list[str]:
    """Passes after the text. Each cell gets bold re-strikes (bold_strikes - 1),
    then an underscore, then the strikethrough mark, one per pass."""
    bold = _codes(profile, "bold") is None  # overstrike bold
    under = _codes(profile, "underline") is None  # overprint underline
    strikes = max(1, int(profile.raw.get("bold_strikes", 2)))
    mark = profile.raw.get("strikethrough", "-")
    marks = []
    for c in cells:
        m = [c.ch] * (strikes - 1) if bold and c.bold and c.ch != " " else []
        if under and c.underline:
            m.append("_")
        if c.strike:
            m.append(mark)
        marks.append(m)
    depth = max(map(len, marks), default=0)
    out = ["".join(m[k] if k < len(m) else " " for m in marks).rstrip() for k in range(depth)]
    return [p for p in out if p]


def _base_pass(cells: list[Cell], profile: Profile) -> bytes:
    bold, under = _codes(profile, "bold"), _codes(profile, "underline")
    out = bytearray()
    on_b = on_u = False
    for c in cells:
        if bold and c.bold != on_b:
            out += bold[0] if c.bold else bold[1]
            on_b = c.bold
        if under and c.underline != on_u:
            out += under[0] if c.underline else under[1]
            on_u = c.underline
        out += encode(c.ch, profile)
    if bold and on_b:
        out += bold[1]
    if under and on_u:
        out += under[1]
    return bytes(out).rstrip(b" ")


def reverse_pass(cells: list[Cell], profile: Profile) -> bytes:
    """A pass that types the non-space cells right to left, so the carrier
    reaches each one from the right. BS flushes the character typed before it
    and moves back a column; the newline or CR after the pass flushes the last."""
    out = bytearray()
    prev = None
    for col in range(len(cells) - 1, -1, -1):
        if cells[col].ch == " ":
            continue
        out += b" " * col if prev is None else BS * (prev + 1 - col)
        out += encode(cells[col].ch, profile)
        prev = col
    return bytes(out)


def render_line(line: Line, profile: Profile) -> bytes:
    """One printed line, ending with a newline."""
    if line.raw is not None:
        return line.raw + newline(profile)
    out = _base_pass(line.cells, profile)
    for p in _overprint_passes(line.cells, profile):
        out += CR + encode(p, profile)
    return out + newline(profile)


def passes(line: Line, profile: Profile) -> int:
    if line.raw is not None:
        return 1 + line.raw.count(CR)
    return 1 + len(_overprint_passes(line.cells, profile))
