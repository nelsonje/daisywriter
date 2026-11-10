"""Calibration pages for a new typewriter or profile.

"margins" types ruler lines one column apart around the right margin, to find
where the firmware's own wrap starts (it must never trigger). "format" types
bold, underline, both and strikethrough, next to plain text, to judge overstrike on the
installed ribbon. "bold" compares ways of re-striking bold text, including
strikes that reach each letter from the right, where play in the carrier
drive might shift them enough to thicken the strokes. "charset" types every character the profile can type.
"""
from __future__ import annotations

from .layout import Cell, Line, Page
from .profile import Profile
from .render import CR, encode, reverse_pass


def _text(s: str, bold=False, underline=False, strike=False) -> list[Cell]:
    return [Cell(ch, bold, underline, strike=strike) for ch in s]


def ruler(n: int) -> str:
    """1234567890 repeated; the last digit shows the column count."""
    return "".join(str((i + 1) % 10) for i in range(n))


def margins_page(profile: Profile) -> Page:
    w = profile.line_width
    lines = [Line(_text(f"Margin probe: rulers of {w - 1} to {w + 3} characters. daisywriter")),
             Line(_text(f"uses {w}. A line that wraps shows where the firmware takes over.")),
             Line()]
    tens = "".join(f"{(i + 1) // 10 % 10}" if (i + 1) % 10 == 0 else " " for i in range(w + 3))
    lines.append(Line(_text(tens.rstrip())))
    for n in range(w - 1, w + 4):
        lines.append(Line(_text(ruler(n))))
    return Page(1, lines)


def format_page(profile: Profile) -> Page:
    sample = "The quick brown fox jumps over the lazy dog."
    lines = [Line(_text("Formatting test: each sample next to plain text.")), Line(),
             Line(_text("plain:      ") + _text(sample)),
             Line(_text("bold:       ") + _text(sample, bold=True)),
             Line(_text("underline:  ") + _text(sample, underline=True)),
             Line(_text("both:       ") + _text(sample, bold=True, underline=True)),
             Line(_text("strikeout:  ") + _text(sample, strike=True)),
             Line(),
             Line(_text("mixed:      a ") + _text("bold", bold=True) + _text(" word, an ")
                  + _text("underlined", underline=True) + _text(" word, and ")
                  + _text("both", bold=True, underline=True) + _text(" together.")),
             Line(_text("underlined spaces:  ") + _text("these words share one line", underline=True)),
             Line(_text("struck out:  a ") + _text("bold", bold=True, strike=True) + _text(" and an ")
                  + _text("underlined", underline=True, strike=True) + _text(" word.")),
             ]
    return Page(1, lines)


def _strikes(label: str, sample: str, profile: Profile, *order: str) -> Line:
    """label + sample typed once, then re-struck once per entry in order:
    "L" types the sample left to right, "R" right to left."""
    cells = _text(" " * len(label) + sample)
    raw = encode(label + sample, profile)
    for way in order:
        raw += CR + (encode(" " * len(label) + sample, profile) if way == "L"
                     else reverse_pass(cells, profile))
    return Line(_text(label + sample), raw=raw)


def bold_page(profile: Profile) -> Page:
    sample = "The quick brown fox jumps over the lazy dog."
    bars = "| " * 10 + "H H H H H"
    rows = [("plain:", ""), ("2, left:", "L"), ("3, left:", "LL"), ("2, right:", "R"),
            ("3, left+right:", "LR"), ("3, right+right:", "RR")]
    lines = [Line(_text("Bold test. Each row is typed once, then re-struck: left = left to")),
             Line(_text("right as usual, right = right to left, reaching each letter from")),
             Line(_text("the right. Compare the rows with plain text under a loupe.")), Line()]
    lines += [_strikes(f"{label:16}", sample, profile, *order) for label, order in rows]
    lines += [Line(), Line(_text("Carrier play: each mark is struck twice. A doubled or thicker")),
              Line(_text("mark in the second row means the carrier stops in a different")),
              Line(_text("place when it comes from the right.")), Line(),
              _strikes(f"{'2, left:':16}", bars, profile, "L"),
              _strikes(f"{'2, right:':16}", bars, profile, "R")]
    return Page(1, lines)


def charset_page(profile: Profile) -> Page:
    ascii_ok = [chr(c) for c in range(0x21, 0x7F) if profile.can_type(chr(c))
                and chr(c) not in profile.charset]
    mapped = list(profile.charset)
    w = profile.line_width
    lines = [Line(_text(f"Character set of the {profile.name}:")), Line()]
    for i in range(0, len(ascii_ok), w // 2):
        lines.append(Line(_text(" ".join(ascii_ok[i:i + w // 2]))))
    if mapped:
        lines += [Line(), Line(_text("Mapped specials: " + " ".join(mapped)))]
    return Page(1, lines)


PAGES = {"margins": margins_page, "format": format_page, "bold": bold_page,
         "charset": charset_page}
