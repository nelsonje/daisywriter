"""Command line: validate and preview mail merges, list profiles, make sample files."""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from . import issues as I
from .layout import LayoutSettings, PageNumbers
from .merge import MergeSettings
from .pipeline import Merge, Settings, run
from .preview import render_html, render_text
from .profile import STOCKS, builtin_profiles
from .values import DEFAULT_DATE


def _letters_arg(text: str) -> set[int]:
    out = set()
    for part in text.split(","):
        a, _, b = part.strip().partition("-")
        try:
            lo, hi = int(a), int(b or a)
        except ValueError:
            raise argparse.ArgumentTypeError(f"bad letter list {text!r} (example: 1,3-5)") from None
        out.update(range(lo, hi + 1))
    return out


def _date_arg(text: str) -> dt.date:
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"bad date {text!r} (use YYYY-MM-DD)") from None


def _merge_args(p: argparse.ArgumentParser):
    p.add_argument("template", type=Path, help="Word template (.docx)")
    p.add_argument("data", type=Path, help="Excel records (.xlsx), first row = headers")
    p.add_argument("--profile", help="typewriter profile id or .toml path (see 'profiles')")
    p.add_argument("--sheet", help="worksheet name (default: the first sheet)")
    p.add_argument("--today", type=_date_arg, help="date used for {{Today}} and DATE fields")
    p.add_argument("--date-format", default=DEFAULT_DATE,
                   help=f"default date format (default: \"{DEFAULT_DATE}\")")
    p.add_argument("--stock", choices=sorted(STOCKS), default="letter", help="paper size")
    p.add_argument("--top", type=int, default=6, help="lines fed before the first typed line")
    p.add_argument("--bottom", type=int, default=6, help="lines left blank at the page bottom")
    p.add_argument("--no-justify", action="store_true", help="type justified paragraphs ragged-right")
    p.add_argument("--page-numbers", choices=["off", "after-first", "all"], default="off")
    p.add_argument("--page-number-position", choices=["top", "bottom"], default="top")
    p.add_argument("--page-number-align", choices=["left", "center", "right"], default="center")
    p.add_argument("--page-number-format", default="- {page} -",
                   help="text with {page}; may use merge fields, e.g. "
                        "\"{{LastName}} - Page {page} - {{Today}}\"")


def _settings(a) -> Settings:
    pn = PageNumbers(a.page_numbers.replace("-", "_"), a.page_number_position,
                     a.page_number_align, a.page_number_format)
    layout = LayoutSettings(stock=a.stock, top_lines=a.top, bottom_lines=a.bottom,
                            justify=not a.no_justify, page_numbers=pn)
    merge = MergeSettings(today=a.today or dt.date.today(), default_date=a.date_format)
    return Settings(profile=a.profile, sheet=a.sheet, merge=merge, layout=layout)


def _run(a) -> Merge:
    for path in (a.template, a.data):
        if not path.exists():
            sys.exit(f"daisywriter: {path} not found")
    try:
        return run(a.template, a.data, _settings(a))
    except ValueError as e:
        sys.exit(f"daisywriter: {e}")


def _print_issues(m: Merge, show_info: bool):
    shown = [i for i in m.all_issues() if show_info or i.level > I.Level.INFO]
    for i in shown:
        print(i)
    counts = {lvl: sum(1 for i in m.all_issues() if i.level is lvl) for lvl in I.Level}
    print(f"\n{len(m.letters)} letters on the {m.profile.name}: "
          f"{counts[I.Level.ERROR]} errors, {counts[I.Level.WARNING]} warnings")


def cmd_validate(a) -> int:
    m = _run(a)
    _print_issues(m, not a.quiet)
    return 1 if not m.ok else 0


def cmd_preview(a) -> int:
    m = _run(a)
    letters = m.letters
    if a.letters:
        letters = [x for x in letters if x.number in a.letters]
        if not letters:
            sys.exit(f"daisywriter: no such letters (there are {len(m.letters)})")
    width = m.profile.line_width
    fmt = a.format
    if fmt == "auto":
        fmt = "html" if a.output and a.output.suffix.lower() in (".html", ".htm") else (
            "ansi" if a.output is None and sys.stdout.isatty() else "plain")
    if fmt == "html":
        text = render_html(letters, len(m.letters), width, f"{a.template.name} + {a.data.name}")
    else:
        text = render_text(letters, len(m.letters), width, ansi=fmt == "ansi")
    if a.output:
        a.output.write_text(text, encoding="utf-8")
        print(f"wrote {a.output}")
    else:
        print(text)
    errors = [i for i in m.all_issues() if i.level is I.Level.ERROR]
    if errors:
        print(f"{len(errors)} errors; run 'daisywriter validate' for details", file=sys.stderr)
    return 1 if errors else 0


def cmd_profiles(a) -> int:
    for pid, p in builtin_profiles().items():
        print(f"{pid:22} {p.name}: {p.pitch_cpi} cpi, {p.lines_per_inch} lpi, margins "
              f"{p.margin_left}-{p.margin_right} ({p.line_width} columns), {p.paper}")
    return 0


def cmd_make_samples(a) -> int:
    from .samples import make_samples
    for path in make_samples(a.directory):
        print(f"wrote {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="daisywriter",
                                 description="Mail merge onto a daisywheel typewriter.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("validate", help="check that a merge can be done")
    _merge_args(p)
    p.add_argument("-q", "--quiet", action="store_true", help="hide info messages")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("preview", help="show the merged letters as they'll be typed")
    _merge_args(p)
    p.add_argument("--letters", type=_letters_arg, help="letters to show, e.g. 1,3-5")
    p.add_argument("--format", choices=["auto", "plain", "ansi", "html"], default="auto")
    p.add_argument("-o", "--output", type=Path, help="write to a file (.html for HTML)")
    p.set_defaults(func=cmd_preview)

    p = sub.add_parser("profiles", help="list built-in typewriter profiles")
    p.set_defaults(func=cmd_profiles)

    p = sub.add_parser("make-samples", help="write a sample template and spreadsheet")
    p.add_argument("directory", type=Path, nargs="?", default=Path("samples"))
    p.set_defaults(func=cmd_make_samples)

    a = ap.parse_args(argv)
    _utf8_output()
    return a.func(a)


def _utf8_output():
    """Previews use box-drawing characters; Windows pipes default to a code page without them."""
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if enc != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
