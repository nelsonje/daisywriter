"""Turn laid-out lines into the bytes a typewriter needs.

Typewriters without bold or underline codes (the Nakajima machines) get them by
typing a line in passes: the text, then CR and a pass with bold re-strikes and
underscores, then (only where a cell is both bold and underlined) a third pass.
CR returns to the left margin without feeding, and leading spaces become
carrier moves, so extra passes cost one carriage return each.
"""
from __future__ import annotations

from .layout import Cell, Line
from .profile import Profile

SO, SI = b"\x0e", b"\x0f"
CR, FF, CAN = b"\r", b"\x0c", b"\x18"


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


def _strike_passes(cells: list[Cell], profile: Profile) -> list[str]:
    bold = _codes(profile, "bold") is None  # overstrike bold
    under = _codes(profile, "underline") is None  # overprint underline
    second, third = [], []
    for c in cells:
        b = bold and c.bold and c.ch != " "
        u = under and c.underline
        second.append(c.ch if b else "_" if u else " ")
        third.append("_" if b and u else " ")
    return [p for p in ("".join(second).rstrip(), "".join(third).rstrip()) if p]


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


def render_line(line: Line, profile: Profile) -> bytes:
    """One printed line, ending with a newline."""
    out = _base_pass(line.cells, profile)
    for p in _strike_passes(line.cells, profile):
        out += CR + encode(p, profile)
    return out + newline(profile)


def passes(line: Line, profile: Profile) -> int:
    return 1 + len(_strike_passes(line.cells, profile))
