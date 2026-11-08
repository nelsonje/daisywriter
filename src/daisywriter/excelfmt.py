"""Render a cell value the way Excel displays it, from the cell's number format.

Covers what letters use: currency, thousands separators, decimals, percent,
zero-padded numbers (ZIP codes), phone/ID patterns, Accounting formats, and
date/time formats. Returns None for formats it doesn't handle (fractions,
"General"), so the caller falls back to its own default. Conventions are US
English, like Excel with US regional settings.
"""
from __future__ import annotations

import datetime as dt
import re

from openpyxl.styles.numbers import BUILTIN_FORMATS

from .values import DAYS, MONTHS

# openpyxl's copies of some built-in formats differ from what Excel shows.
_BUILTIN_FIXES = {
    BUILTIN_FORMATS[14]: "m/d/yyyy",  # "short date": Excel shows the regional short date
    BUILTIN_FORMATS[41]: '_(* #,##0_);_(* \\(#,##0\\);_(* "-"_);_(@_)',
    BUILTIN_FORMATS[42]: '_("$"* #,##0_);_("$"* \\(#,##0\\);_("$"* "-"_);_(@_)',
    BUILTIN_FORMATS[43]: '_(* #,##0.00_);_(* \\(#,##0.00\\);_(* "-"??_);_(@_)',
    BUILTIN_FORMATS[44]: '_("$"* #,##0.00_);_("$"* \\(#,##0.00\\);_("$"* "-"??_);_(@_)',
}

EXCEL_EPOCH = dt.datetime(1899, 12, 30)


def format_excel(value, number_format: str | None) -> str | None:
    """The text Excel shows for value, or None to use the default formatting."""
    fmt = _BUILTIN_FIXES.get(number_format, number_format)
    if not fmt or fmt == "General" or value is None or isinstance(value, bool):
        return None
    sections = _split_sections(fmt)
    if isinstance(value, str):
        if len(sections) >= 4:
            return _text_section(sections[3], value)
        if len(sections) == 1 and "@" in _strip_literals(sections[0]):
            return _text_section(sections[0], value)
        return None
    section, number, signed = _choose_section(sections, value)
    if section is None:
        return None
    items = _tokenize(section)
    if _is_date(items):
        when = _as_datetime(value)
        return None if when is None else _render_date(items, when).strip()
    if isinstance(value, (dt.date, dt.time)):
        return None
    if any(kind == "lit" and text == "/" for kind, text in items):
        return None  # fractions such as "# ?/?"
    out = _render_number(items, number)
    if out is None:
        return None
    return (("-" if signed and number != 0 and not _all_zero(out) else "") + out).strip()


# ---------------------------------------------------------------- parsing

def _split_sections(fmt: str) -> list[str]:
    out, cur, i = [], [], 0
    while i < len(fmt):
        ch = fmt[i]
        if ch == '"':
            j = fmt.find('"', i + 1)
            j = len(fmt) - 1 if j < 0 else j
            cur.append(fmt[i:j + 1])
            i = j + 1
            continue
        if ch == "\\" and i + 1 < len(fmt):
            cur.append(fmt[i:i + 2])
            i += 2
            continue
        if ch == "[":
            j = fmt.find("]", i)
            j = len(fmt) - 1 if j < 0 else j
            cur.append(fmt[i:j + 1])
            i = j + 1
            continue
        if ch == ";":
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    out.append("".join(cur))
    return out


_CONDITION = re.compile(r"\[(<=|>=|<>|<|>|=)(-?\d+(?:\.\d+)?)\]")


def _condition(section: str):
    m = _CONDITION.search(section)
    if not m:
        return None
    op, limit = m.group(1), float(m.group(2))
    return {"<": lambda v: v < limit, ">": lambda v: v > limit, "=": lambda v: v == limit,
            "<=": lambda v: v <= limit, ">=": lambda v: v >= limit,
            "<>": lambda v: v != limit}[op]


def _choose_section(sections: list[str], value):
    """Return (section, number to show, whether to add a minus sign)."""
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return sections[0], value, False
    if not isinstance(value, (int, float)):
        return None, None, False
    conds = [_condition(s) for s in sections[:3]]
    if any(conds):
        for s, c in zip(sections[:3], conds):
            if c is None or c(value):
                return s, abs(value), value < 0 and c is None
        return None, None, False
    if value > 0 or len(sections) == 1:
        return sections[0], abs(value), value < 0
    if value < 0:
        return sections[1], abs(value), False
    return (sections[2] if len(sections) > 2 else sections[0]), 0, False


def _tokenize(section: str) -> list[tuple[str, str]]:
    """Split a section into ("lit", text) and ("code", chars) items."""
    items: list[tuple[str, str]] = []
    i = 0
    while i < len(section):
        ch = section[i]
        for ampm in ("am/pm", "a/p"):
            if section[i:i + len(ampm)].lower() == ampm:
                items.append(("code", section[i:i + len(ampm)]))
                i += len(ampm)
                break
        else:
            ampm = None
        if ampm:
            continue
        if ch == '"':
            j = section.find('"', i + 1)
            j = len(section) if j < 0 else j
            items.append(("lit", section[i + 1:j]))
            i = j + 1
        elif ch == "\\" and i + 1 < len(section):
            items.append(("lit", section[i + 1]))
            i += 2
        elif ch == "_" and i + 1 < len(section):
            items.append(("lit", " "))  # space as wide as the next character
            i += 2
        elif ch == "*" and i + 1 < len(section):
            i += 2  # repeat-to-fill: nothing on a typewriter
        elif ch == "[":
            j = section.find("]", i)
            j = len(section) - 1 if j < 0 else j
            inner = section[i + 1:j]
            if inner.startswith("$"):
                symbol = inner[1:].split("-", 1)[0]
                if symbol:
                    items.append(("lit", symbol))
            elif inner.lower() in ("h", "hh", "m", "mm", "s", "ss"):
                items.append(("code", inner.lower()))
            i = j + 1  # colors, conditions and locales print nothing
        elif ch in "$-+/():!^&'~{}<>=  ,":
            items.append(("lit" if ch != "," else "code", ch))
            i += 1
        else:
            items.append(("code", ch))
            i += 1
    return items


def _strip_literals(section: str) -> str:
    return "".join(t for k, t in _tokenize(section) if k == "code")


def _text_section(section: str, text: str) -> str:
    out = []
    for kind, t in _tokenize(section):
        out.append(text if kind == "code" and t == "@" else (t if kind == "lit" else ""))
    return "".join(out).strip()


# ---------------------------------------------------------------- dates

def _is_date(items) -> bool:
    codes = "".join(t for k, t in items if k == "code").lower()
    return bool(re.search(r"[ydhs]|m", codes)) and not re.search(r"[0#?]", codes.replace(".0", ""))


def _as_datetime(value):
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return dt.datetime(value.year, value.month, value.day)
    if isinstance(value, dt.time):
        return dt.datetime.combine(EXCEL_EPOCH.date(), value)
    if isinstance(value, (int, float)) and 0 <= value < 2958466:
        return EXCEL_EPOCH + dt.timedelta(days=value)
    return None


def _date_tokens(items):
    """Group date codes into runs such as "mmmm" or "yy"; keep literals."""
    codes = []
    # join consecutive code characters, then split into runs
    merged = []
    for kind, t in items:
        if kind == "code" and merged and merged[-1][0] == "code":
            merged[-1] = ("code", merged[-1][1] + t)
        else:
            merged.append((kind, t))
    for kind, t in merged:
        if kind == "lit":
            codes.append(("lit", t))
            continue
        i = 0
        while i < len(t):
            low = t.lower()
            if low.startswith("am/pm", i):
                codes.append(("ampm", t[i:i + 5]))  # keeps the format's case
                i += 5
                continue
            if low.startswith("a/p", i):
                codes.append(("ap", t[i:i + 3]))
                i += 3
                continue
            ch = low[i]
            j = i
            while j < len(t) and low[j] == ch:
                j += 1
            if ch in "ymdhs":
                codes.append((ch, j - i))
            elif ch == "." and j < len(t) and low[j] == "0":
                k = j
                while k < len(t) and low[k] == "0":
                    k += 1
                codes.append(("frac", k - j))
                j = k
            else:
                codes.append(("lit", t[i:j]))
            i = j
    # "m" after an hour or before a second is minutes
    kinds = [k for k, _ in codes]
    for idx, (k, n) in enumerate(codes):
        if k != "m" or n > 2:
            continue
        before = next((kinds[b] for b in range(idx - 1, -1, -1) if kinds[b] != "lit"), None)
        after = next((kinds[a] for a in range(idx + 1, len(codes)) if kinds[a] != "lit"), None)
        if before == "h" or after == "s":
            codes[idx] = ("min", n)
    return codes


def _render_date(items, when: dt.datetime) -> str:
    codes = _date_tokens(items)
    twelve = any(k in ("ampm", "ap") for k, _ in codes)
    out = []
    for k, n in codes:
        if k == "lit":
            out.append(n)
        elif k == "y":
            out.append(f"{when.year % 100:02d}" if n <= 2 else f"{when.year:04d}")
        elif k == "m":
            name = MONTHS[when.month - 1]
            out.append({1: str(when.month), 2: f"{when.month:02d}", 3: name[:3], 4: name}.get(n, name[0]))
        elif k == "d":
            day = DAYS[when.weekday()]
            out.append({1: str(when.day), 2: f"{when.day:02d}", 3: day[:3]}.get(n, day))
        elif k == "h":
            h = when.hour % 12 or 12 if twelve else when.hour
            out.append(str(h) if n == 1 else f"{h:02d}")
        elif k == "min":
            out.append(str(when.minute) if n == 1 else f"{when.minute:02d}")
        elif k == "s":
            out.append(str(when.second) if n == 1 else f"{when.second:02d}")
        elif k == "frac":
            out.append("." + f"{when.microsecond:06d}"[:n])
        elif k in ("ampm", "ap"):  # printed in the case the format uses
            am, pm = n.split("/")
            out.append(am if when.hour < 12 else pm)
    return "".join(out)


# ---------------------------------------------------------------- numbers

def _all_zero(text: str) -> bool:
    return not re.search(r"[1-9]", text)


def _render_number(items, value: float) -> str | None:
    codes = [(k, t) for k, t in items]
    if any(k == "code" and t.lower() == "e" for k, t in codes):
        return _render_scientific(codes, value)
    if any(k == "code" and t not in "0#?.,%" for k, t in codes):
        return None  # something we don't understand
    places = [i for i, (k, t) in enumerate(codes) if k == "code" and t in "0#?"]
    if not places:
        return "".join(t for k, t in codes if k == "lit" or t == "%")
    dot = next((i for i, (k, t) in enumerate(codes) if k == "code" and t == "."), None)
    int_places = [i for i in places if dot is None or i < dot]
    frac_places = [i for i in places if dot is not None and i > dot]

    # commas right after the last digit or before the decimal point scale by 1000;
    # commas between integer digits group thousands
    last_int = int_places[-1] if int_places else -1
    scale = 0
    for start in {places[-1] + 1, last_int + 1}:
        j = start
        while 0 < j < len(codes) and codes[j] == ("code", ","):
            scale += 1
            j += 1
    grouping = any(codes[i] == ("code", ",") for i in range(int_places[0], last_int)) if int_places else False
    value = value / (1000 ** scale)
    value *= 100 ** sum(1 for k, t in codes if k == "code" and t == "%")

    text = f"{value:.{len(frac_places)}f}"
    int_digits, _, frac_digits = text.partition(".")
    if int_digits == "0":
        int_digits = ""

    out = [t if k == "lit" else "" for k, t in codes]
    for i, (k, t) in enumerate(codes):
        if k == "code" and t in ".%":
            out[i] = t

    # integer digits fill the placeholders from the right
    literal_between = any(codes[i][0] == "lit" for i in range(int_places[0], last_int)) if int_places else False
    if int_places and grouping and not literal_between:
        if int_digits or any(codes[i][1] == "0" for i in int_places):
            out[int_places[0]] = f"{int(int_digits or 0):,}"
    elif int_places:
        remaining = int_digits
        for n, i in enumerate(reversed(int_places)):
            ph = codes[i][1]
            if n == len(int_places) - 1:  # leftmost placeholder takes any extra digits
                out[i] = remaining or ("0" if ph == "0" else " " if ph == "?" else "")
                remaining = ""
            elif remaining:
                out[i], remaining = remaining[-1], remaining[:-1]
            else:
                out[i] = "0" if ph == "0" else " " if ph == "?" else ""

    # fraction digits fill from the left; optional trailing zeros disappear
    keep = len(frac_digits)
    while keep > 0 and frac_digits[keep - 1] == "0" and codes[frac_places[keep - 1]][1] != "0":
        keep -= 1
    for n, i in enumerate(frac_places):
        ph = codes[i][1]
        if n < keep:
            out[i] = frac_digits[n]
        else:
            out[i] = " " if ph == "?" else ""
    return "".join(out)


def _render_scientific(codes, value: float) -> str | None:
    text = "".join(t for _, t in codes)
    m = re.fullmatch(r"([^0#?]*)([0#?]+)(?:\.([0#?]+))?[eE]([+-])([0#]+)(.*)", text)
    if not m:
        return None
    prefix, _, frac, sign, exp, suffix = m.groups()
    mant, e = f"{value:.{len(frac or '')}E}".split("E")
    e = int(e)
    esign = "-" if e < 0 else ("+" if sign == "+" else "")
    return f"{prefix}{mant}E{esign}{abs(e):0{len(exp)}d}{suffix}"
