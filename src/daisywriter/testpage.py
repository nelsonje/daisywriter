"""Calibration pages for a new typewriter or profile.

"margins" types ruler lines one column apart around the right margin, to find
where the firmware's own wrap starts (it must never trigger). "format" types
bold, underline and both, next to plain text, to judge overstrike on the
installed ribbon. "charset" types every character the profile can type.
"""
from __future__ import annotations

from .layout import Cell, Line, Page
from .profile import Profile


def _text(s: str, bold=False, underline=False) -> list[Cell]:
    return [Cell(ch, bold, underline) for ch in s]


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
             Line(),
             Line(_text("mixed:      a ") + _text("bold", bold=True) + _text(" word, an ")
                  + _text("underlined", underline=True) + _text(" word, and ")
                  + _text("both", bold=True, underline=True) + _text(" together.")),
             Line(_text("underlined spaces:  ") + _text("these words share one line", underline=True)),
             ]
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


PAGES = {"margins": margins_page, "format": format_page, "charset": charset_page}
