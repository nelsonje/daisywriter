"""Simulated typing errors with strikeover corrections, so a letter looks typed by hand.

Errors go only into the letter body (docs/PLAN.md §7), never into text that
came from a merge field (a recipient's name is never misspelled), and never
into the first or last word of a paragraph. Each error is one of:
- substitution: a neighbouring key on a QWERTY keyboard ("tje" for "the")
- transposition: two letters swapped ("teh")
- doubled letter ("thhe")
- skipped letter ("te")

and is corrected the way a typist would:
- x-out: the typed part of the word, up to a letter or two past the mistake,
  is struck over with x, and the word follows, typed correctly after a space
- overstrike: the right letter is struck over the wrong one, in place. Only
  substitutions can be fixed this way; the others fall back to x-out.

The result is spans whose `over` holds the characters struck over each of
their characters. Layout and rendering carry them through to the typewriter.

The errors are random but reproducible: each letter's seed comes from the
template, the spreadsheet row and its values, and a salt the user can change
("re-roll"), so printing again gives the same errors as the preview.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field, replace

from .model import Paragraph, Span

ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
KINDS = [("substitution", 0.4), ("transposition", 0.25), ("doubled", 0.2), ("skipped", 0.15)]
STYLES = ("mix", "xout", "overstrike")


def _neighbours() -> dict[str, str]:
    out = {}
    for r, row in enumerate(ROWS):
        for i, ch in enumerate(row):
            near = [row[j] for j in (i - 1, i + 1) if 0 <= j < len(row)]
            if r > 0:  # the row above sits half a key to the left
                near += [ROWS[r - 1][j] for j in (i, i + 1) if j < len(ROWS[r - 1])]
            if r < len(ROWS) - 1:
                near += [ROWS[r + 1][j] for j in (i - 1, i) if 0 <= j < len(ROWS[r + 1])]
            out[ch] = "".join(near)
    return out


NEIGHBOURS = _neighbours()


@dataclass
class ErrorSettings:
    enabled: bool = False
    rate: float = 1.0  # errors per 100 words of body text, on average
    style: str = "mix"  # "mix" | "xout" | "overstrike"
    salt: int = 0  # change to give every letter different errors
    letter_salts: dict[str, int] = field(default_factory=dict)  # re-rolls, by session.letter_key
    min_gap: int = 12  # words between errors, at least

    def __post_init__(self):
        if self.style not in STYLES:
            raise ValueError(f"typing error style {self.style!r} isn't one of {', '.join(STYLES)}")


@dataclass(frozen=True)
class TypingError:
    paragraph: int  # template paragraph index
    word: str
    typed: str  # the word as mistyped
    kind: str
    style: str  # how it was corrected: "xout" or "overstrike"


def seed_for(key: str, settings: ErrorSettings) -> int:
    text = f"{key}|{settings.salt}|{settings.letter_salts.get(key, 0)}"
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")


def _mistype(word: str, rng: random.Random) -> tuple[str, int, str] | None:
    """(typed, index of the first wrong letter, kind), or None if no error fits."""
    kind = rng.choices([k for k, _ in KINDS], [w for _, w in KINDS])[0]
    i = rng.randrange(1, len(word))  # typists rarely get a word's first letter wrong
    if kind == "substitution":
        near = NEIGHBOURS.get(word[i].lower())
        if not near or word[i] in "xX":  # a correcting x would look like an x-out
            return None
        wrong = rng.choice(near)
        return word[:i] + (wrong.upper() if word[i].isupper() else wrong) + word[i + 1:], i, kind
    if kind == "transposition":
        i = min(i, len(word) - 2)
        if word[i] == word[i + 1]:
            return None
        return word[:i] + word[i + 1] + word[i] + word[i + 2:], i, kind
    if kind == "doubled":
        return word[:i + 1] + word[i] + word[i + 1:], i + 1, kind
    return word[:i] + word[i + 1:], i, kind  # skipped


def _corrected(span: Span, start: int, end: int, typed: str, at: int, kind: str, style: str,
               rng: random.Random) -> list[Span]:
    """span with its text[start:end] (a word) mistyped as typed and corrected."""
    word = span.text[start:end]
    before, after = replace(span, text=span.text[:start]), replace(span, text=span.text[end:])
    if style == "overstrike":
        return [before, replace(span, text=word[:at]), replace(span, text=typed[at], over=word[at]),
                replace(span, text=word[at + 1:]), after]
    noticed = min(len(typed), at + 1 + rng.randrange(3))  # a letter or two later, or at the word's end
    return [before, replace(span, text=typed[:noticed], over="x"), replace(span, text=" ", over=""),
            replace(span, text=word), after]


def _words(text: str) -> list[tuple[int, int]]:
    out, start = [], None
    for k, ch in enumerate(text + " "):
        if ch.isalpha() and ch.isascii():
            if start is None:
                start = k
        elif start is not None:
            out.append((start, k))
            start = None
    return out


def add_typing_errors(paragraphs: list[Paragraph], settings: ErrorSettings,
                      seed: int) -> tuple[list[Paragraph], list[TypingError]]:
    rng = random.Random(seed)
    p_error = max(0.0, settings.rate) / 100
    gap = settings.min_gap  # words since the last error; start ready for one
    out, made = [], []
    for para in paragraphs:
        # words, in order, as (span index, start, end, eligible?)
        words = [(si, a, b, s.body and not s.from_field and not s.over and b - a >= 3)
                 for si, s in enumerate(para.spans) for a, b in _words(s.text)]
        if not any(w[3] for w in words):
            out.append(para)
            gap += len(words)
            continue
        plan: dict[int, list] = {}
        for n, (si, a, b, ok) in enumerate(words):
            gap += 1
            if not ok or n == 0 or n == len(words) - 1 or gap <= settings.min_gap:
                continue
            if rng.random() >= p_error:
                continue
            word = para.spans[si].text[a:b]
            mistake = _mistype(word, rng)
            if mistake is None:
                continue
            typed, at, kind = mistake
            style = settings.style
            if style == "mix":
                style = "overstrike" if kind == "substitution" and rng.random() < 0.5 else "xout"
            elif style == "overstrike" and kind != "substitution":
                style = "xout"
            plan.setdefault(si, []).append((a, b, typed, at, kind, style))
            made.append(TypingError(para.index, word, typed, kind, style))
            gap = 0
        if not plan:
            out.append(para)
            continue
        spans: list[Span] = []
        for si, span in enumerate(para.spans):
            pieces = [span]
            # right to left, so the first piece always holds the text before the next error
            for a, b, typed, at, kind, style in sorted(plan.get(si, []), reverse=True):
                pieces = _corrected(pieces.pop(0), a, b, typed, at, kind, style, rng) + pieces
            spans += [s for s in pieces if s.text]
        out.append(para.copy_with(spans))
    return out, made


def intended_text(spans: list[Span]) -> str:
    """The text a reader takes from corrected spans: x-outs and the space after
    them dropped, overstruck letters read as the letter struck over them."""
    out, skip_space = [], False
    for s in spans:
        if s.over == "x":
            skip_space = True
            continue
        text = s.over * len(s.text) if s.over else s.text
        if skip_space and text.startswith(" "):
            text = text[1:]
        skip_space = False
        out.append(text)
    return "".join(out)
