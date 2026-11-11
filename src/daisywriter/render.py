"""Turn laid-out lines into the bytes a typewriter needs.

Typewriters without bold or underline codes (the Nakajima machines) get them by
typing a line in passes: the text, then CR and passes with bold re-strikes,
underscores and strikethrough marks. A bold re-strike pass can run right to
left (see bold_restrikes); the other marks share left-to-right passes where
their columns are free. CR returns to the left margin without feeding, and leading
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


def bold_restrikes(profile: Profile) -> list[str]:
    """Direction of each bold re-strike pass: "left" types left to right as usual,
    "right" types right to left so the carrier reaches each letter from the right,
    where play in the carrier drive shifts it slightly (a shadow)."""
    ways = profile.raw.get("bold_restrikes", ["left"])
    for w in ways:
        if w not in ("left", "right"):
            raise ValueError(f"bold_restrikes: {w!r} isn't \"left\" or \"right\"")
    return list(ways)


def _overprint_passes(cells: list[Cell], profile: Profile) -> list[tuple[str, str]]:
    """(direction, text) passes after the text. Bold cells are re-struck once in
    each bold_restrikes pass. Underscores and strikethrough marks then go into
    the first left-to-right pass that is free at their column, or new ones."""
    bold = _codes(profile, "bold") is None  # overstrike bold
    under = _codes(profile, "underline") is None  # overprint underline
    mark = profile.raw.get("strikethrough", "-")
    ways = bold_restrikes(profile) if bold and any(c.bold and c.ch != " " for c in cells) else []
    grid = [[c.ch if c.bold and c.ch != " " else " " for c in cells] for _ in ways]
    for i, c in enumerate(cells):
        for m in ("_" if under and c.underline else "", mark if c.strike else ""):
            if not m:
                continue
            k = next((k for k, w in enumerate(ways) if w == "left" and grid[k][i] == " "), None)
            if k is None:
                ways.append("left")
                grid.append([" "] * len(cells))
                k = len(ways) - 1
            grid[k][i] = m
    out = [(w, "".join(g).rstrip()) for w, g in zip(ways, grid, strict=True)]
    return [(w, t) for w, t in out if t]


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


def _cells(text: str) -> list[Cell]:
    return [Cell(ch) for ch in text]


def render_line(line: Line, profile: Profile) -> bytes:
    """One printed line, ending with a newline."""
    if line.raw is not None:
        return line.raw + newline(profile)
    out = _base_pass(line.cells, profile)
    for way, text in _overprint_passes(line.cells, profile):
        out += CR + (encode(text, profile) if way == "left" else reverse_pass(_cells(text), profile))
    return out + newline(profile)


def passes(line: Line, profile: Profile) -> int:
    if line.raw is not None:
        return 1 + line.raw.count(CR)
    return 1 + len(_overprint_passes(line.cells, profile))
