"""Turn Excel cell values into text, using Word-style format pictures.

Dates are always formatted here, from the cell's value; Excel's own display
format is ignored. Month and day names are English and don't depend on the
computer's locale settings.
"""
from __future__ import annotations

import datetime as dt
import re

from .model import FieldRef

DEFAULT_DATE = "MMMM d, yyyy"

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_DATE_TOKENS = ["yyyy", "yy", "MMMM", "MMM", "MM", "M", "dddd", "ddd", "dd", "d",
                "HH", "H", "hh", "h", "mm", "m", "ss", "s", "AM/PM", "am/pm"]


def is_date_picture(picture: str) -> bool:
    bare = re.sub(r"'[^']*'", "", picture)
    return bool(re.search(r"[yMd]", bare)) and not re.search(r"[#0]", bare)


def format_date(value: dt.date | dt.datetime, picture: str = DEFAULT_DATE) -> str:
    out, i = [], 0
    hour = value.hour if isinstance(value, dt.datetime) else 0
    minute = value.minute if isinstance(value, dt.datetime) else 0
    second = value.second if isinstance(value, dt.datetime) else 0
    while i < len(picture):
        if picture[i] == "'":
            j = picture.find("'", i + 1)
            j = len(picture) if j < 0 else j
            out.append(picture[i + 1:j])
            i = j + 1
            continue
        for tok in _DATE_TOKENS:
            if picture.startswith(tok, i):
                out.append(_date_token(tok, value, hour, minute, second))
                i += len(tok)
                break
        else:
            out.append(picture[i])
            i += 1
    return "".join(out)


def _date_token(tok, v, hour, minute, second) -> str:
    h12 = hour % 12 or 12
    return {
        "yyyy": f"{v.year:04d}", "yy": f"{v.year % 100:02d}",
        "MMMM": MONTHS[v.month - 1], "MMM": MONTHS[v.month - 1][:3],
        "MM": f"{v.month:02d}", "M": str(v.month),
        "dddd": DAYS[v.weekday()], "ddd": DAYS[v.weekday()][:3],
        "dd": f"{v.day:02d}", "d": str(v.day),
        "HH": f"{hour:02d}", "H": str(hour), "hh": f"{h12:02d}", "h": str(h12),
        "mm": f"{minute:02d}", "m": str(minute), "ss": f"{second:02d}", "s": str(second),
        "AM/PM": "AM" if hour < 12 else "PM", "am/pm": "am" if hour < 12 else "pm",
    }[tok]


_NUMBER_CORE = re.compile(r"[#0][#0,]*(\.[#0]+)?|\.[#0]+")


def format_number(value: float, picture: str) -> str:
    """Format with a Word numeric picture such as "#,##0.00", "$#,##0" or "0.0%"."""
    m = _NUMBER_CORE.search(picture)
    if not m:
        return default_number(value)
    prefix, core, suffix = picture[:m.start()], m.group(0), picture[m.end():]
    if "%" in suffix:
        value = value * 100
    decimals = len(core.split(".", 1)[1]) if "." in core else 0
    grouping = "," if "," in core else ""
    text = f"{abs(value):{grouping}.{decimals}f}"
    sign = "-" if value < 0 and float(text.replace(",", "")) != 0 else ""
    return f"{sign}{prefix}{text}{suffix}"


def default_number(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, float):
        return f"{value:.10g}"
    return str(value)


def _parse_iso(text: str):
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return dt.date.fromisoformat(text)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?", text):
            return dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    return None


def apply_case(text: str, case: str | None) -> str:
    if case == "upper":
        return text.upper()
    if case == "lower":
        return text.lower()
    if case == "caps":
        return re.sub(r"[A-Za-z][^\s-]*", lambda m: m.group(0)[0].upper() + m.group(0)[1:], text)
    if case == "firstcap":
        return text[:1].upper() + text[1:]
    return text


def format_value(value, ref: FieldRef, default_date: str = DEFAULT_DATE,
                 excel_format: str | None = None) -> tuple[str, str | None]:
    """Return (text, problem). problem is a message when the picture didn't fit the value.

    A format in the template wins; otherwise the value is shown as Excel shows it
    (excel_format); otherwise numbers print plainly and dates as default_date.
    """
    problem = None
    pic = ref.picture
    if not pic and excel_format:
        from .excelfmt import format_excel  # excelfmt imports month names from here

        shown = format_excel(value, excel_format)
        if shown is not None:
            text = apply_case(shown, ref.case)
            return (ref.before + text + ref.after if text else text), None
    date_pic = pic if pic and (ref.kind == "date" or (ref.kind is None and is_date_picture(pic))) else None
    num_pic = pic if pic and not date_pic and ref.kind != "date" else None

    if isinstance(value, str):
        value = value.strip()
        if date_pic:
            parsed = _parse_iso(value)
            if parsed is not None:
                value = parsed
            else:
                problem = f"date format \"{pic}\" given, but the value \"{value}\" isn't a date"

    if value is None:
        text = ""
    elif isinstance(value, bool):
        text = "TRUE" if value else "FALSE"
    elif isinstance(value, (dt.datetime, dt.date)):
        if num_pic:
            problem = f"number format \"{pic}\" given, but the value is a date"
        text = format_date(value, date_pic or default_date)
    elif isinstance(value, dt.time):
        text = format_date(dt.datetime.combine(dt.date(2000, 1, 1), value), date_pic or "h:mm AM/PM")
    elif isinstance(value, (int, float)):
        if date_pic:
            problem = f"date format \"{pic}\" given, but the value {default_number(value)} isn't a date"
        text = format_number(value, num_pic) if num_pic else default_number(value)
    else:
        text = str(value)

    text = apply_case(text, ref.case)
    if text:
        text = ref.before + text + ref.after
    return text, problem
