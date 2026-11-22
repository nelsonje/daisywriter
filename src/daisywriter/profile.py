"""Typewriter profiles (TOML) and the characters each machine can type."""
from __future__ import annotations

import tomllib
import unicodedata
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

# Replacements used when the wheel lacks the original character.
SUBSTITUTIONS = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "−": "-",
    "—": "--", "―": "--", "…": "...", "•": "*", "·": "*",
    " ": " ", " ": " ", " ": " ", " ": " ", " ": " ", " ": " ",
    "\u200b": "", "­": "", "⁠": "", "﻿": "",
    "½": "1/2", "¼": "1/4", "¾": "3/4", "×": "x",
    "©": "(c)", "®": "(R)", "™": "(TM)",
}
CONTROL = "\t\n\f"


@dataclass(frozen=True)
class Stock:
    name: str
    width_in: float
    length_in: float

    @property
    def label(self) -> str:
        size = f"{inches(self.width_in)} × {inches(self.length_in)} in"
        return f"{self.name.title() if self.name != 'a4' else 'A4'} ({size})" if self.name in STOCKS else size


STOCKS = {
    "letter": Stock("letter", 8.5, 11.0),
    "legal": Stock("legal", 8.5, 14.0),
    "a4": Stock("a4", 8.27, 11.69),
}
LETTER = STOCKS["letter"]


def sized(width_in: float, length_in: float) -> Stock:
    """A named stock if the size is one (within 1/50 in), else a custom one."""
    for s in STOCKS.values():
        if abs(s.width_in - width_in) < 0.02 and abs(s.length_in - length_in) < 0.02:
            return s
    return Stock("custom", round(width_in, 3), round(length_in, 3))


def paper_size(spec: str | Stock) -> Stock:
    """letter, legal, a4, or WIDTHxLENGTH in inches (e.g. 6.125x11)."""
    if isinstance(spec, Stock):
        return spec
    key = spec.strip().lower()
    if key in STOCKS:
        return STOCKS[key]
    w, sep, h = key.replace(" ", "").replace("×", "x").partition("x")
    try:
        width, length = float(w), float(h)
    except ValueError:
        width = length = 0
    if not sep or not (1 <= width <= 30 and 1 <= length <= 40):
        raise ValueError(f"unknown paper size {spec!r}; use {', '.join(STOCKS)} or WIDTHxLENGTH "
                         "in inches, e.g. 6.125x11")
    return sized(width, length)


_FRACTIONS = {8: "⅛¼⅜½⅝¾⅞", 6: "⅙⅓½⅔⅚"}  # eighths of an inch, and sixths (lines at 6 lpi)


def inches(x: float) -> str:
    """Inches for people: 6⅛, ¾, ⅔, 1, 8.27."""
    for n, signs in _FRACTIONS.items():
        if abs(x * n - round(x * n)) < 0.01:
            whole, part = divmod(round(x * n), n)
            return (str(whole) if whole or not part else "") + (signs[part - 1] if part else "")
    return f"{x:.2f}".rstrip("0").rstrip(".")


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    pitch_cpi: int
    lines_per_inch: int
    margin_left: int
    margin_right: int
    right_guard: int = 1
    paper: str = "single_sheet"
    load_offset_lines: int = 0  # printing point below the sheet's top edge once it's loaded
    eject_extra_lines: int = 0  # extra feed after the bottom edge reaches the printing point
    unavailable: frozenset[str] = frozenset()
    charset: dict[str, bytes] = field(default_factory=dict)
    raw: dict = field(default_factory=dict, compare=False)

    @property
    def line_width(self) -> int:
        """Columns available for text between the margins.

        Measured on the Swintec 1146 CMP (testpage margins): with margins 10/75 a
        66-character line fits and a 67th character wraps, so the right-margin
        column itself is usable.
        """
        return self.margin_right - self.margin_left + 1 - self.right_guard

    @property
    def text_end(self) -> int:
        """The column after the last one the typewriter types without wrapping."""
        return self.margin_left + self.line_width

    @property
    def line_pt(self) -> float:
        return 72.0 / self.lines_per_inch

    def pt_to_cols(self, pt: float) -> int:
        return round(pt / 72.0 * self.pitch_cpi)

    def can_type(self, ch: str) -> bool:
        if ch in self.charset or ch in CONTROL:
            return True
        return " " <= ch <= "~" and ch not in self.unavailable

    def typeable(self, text: str) -> tuple[str, list[tuple[str, str]], list[str]]:
        """Map text onto the wheel.

        Returns (text, substituted, missing): substituted lists (original, replacement)
        pairs that change how the text reads (accents dropped), missing lists
        characters that can't be typed at all. Quote and dash substitutions are silent.
        """
        out, subs, missing = [], [], []
        for ch in text:
            if self.can_type(ch):
                out.append(ch)
                continue
            rep = SUBSTITUTIONS.get(ch)
            if rep is not None and all(self.can_type(c) for c in rep):
                out.append(rep)
                continue
            base = "".join(c for c in unicodedata.normalize("NFKD", ch)
                           if not unicodedata.combining(c))
            if base and base != ch and all(self.can_type(c) for c in base):
                out.append(base)
                subs.append((ch, base))
                continue
            out.append(ch)
            missing.append(ch)
        return "".join(out), subs, missing


def _from_toml(pid: str, data: dict) -> Profile:
    margins = data.get("margins", {})
    return Profile(
        id=pid,
        name=data.get("name", pid),
        pitch_cpi=int(data.get("pitch_cpi", 10)),
        lines_per_inch=int(data.get("lines_per_inch", 6)),
        margin_left=int(margins.get("left", 10)),
        margin_right=int(margins.get("right", 75)),
        right_guard=int(data.get("right_guard", 1)),
        paper=data.get("paper", "single_sheet"),
        load_offset_lines=int(data.get("load_offset_lines", 0)),
        eject_extra_lines=int(data.get("eject_extra_lines", 0)),
        unavailable=frozenset(data.get("unavailable", "")),
        charset={k: v.encode("latin-1") for k, v in data.get("charset", {}).items()},
        raw=data,
    )


def builtin_profiles() -> dict[str, Profile]:
    out = {}
    for entry in sorted(resources.files("daisywriter.profiles").iterdir(), key=lambda e: e.name):
        if entry.name.endswith(".toml"):
            pid = entry.name.removesuffix(".toml")
            out[pid] = _from_toml(pid, tomllib.loads(entry.read_text(encoding="utf-8")))
    return out


DEFAULT_PROFILE = "swintec-1146cmp"


def load_profile(name_or_path: str | None = None) -> Profile:
    """A built-in profile id, or a path to a .toml file."""
    name_or_path = name_or_path or DEFAULT_PROFILE
    path = Path(name_or_path)
    if path.suffix == ".toml" and path.exists():
        return _from_toml(path.stem, tomllib.loads(path.read_text(encoding="utf-8")))
    profiles = builtin_profiles()
    if name_or_path not in profiles:
        raise ValueError(f"unknown profile {name_or_path!r}; built-in profiles: "
                         f"{', '.join(profiles)}")
    return profiles[name_or_path]
