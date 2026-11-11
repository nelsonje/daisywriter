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
from .profile import STOCKS, builtin_profiles, load_profile
from .transports import TransportError
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
                   help=f"date format for {{{{Today}}}} and dates Excel shows as General "
                        f"(default: \"{DEFAULT_DATE}\")")
    p.add_argument("--ignore-excel-formats", action="store_true",
                   help="don't show values as formatted in Excel (template formats still apply)")
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
    merge = MergeSettings(today=a.today or dt.date.today(), default_date=a.date_format,
                          excel_formats=not a.ignore_excel_formats)
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


def _ask(message: str) -> bool:
    try:
        answer = input(f"{message} [Enter = yes, q = quit] ")
    except EOFError:
        return False
    return answer.strip().lower() not in ("q", "quit", "n", "no")


def _print_args(p: argparse.ArgumentParser, merge: bool):
    if not merge:
        p.add_argument("--profile", help="typewriter profile id or .toml path (see 'profiles')")
        p.add_argument("--top", type=int, default=6, help="lines fed before the first typed line")
    out = p.add_mutually_exclusive_group()
    out.add_argument("--dry-run", metavar="FILE", help="write the bytes to FILE instead of printing")
    out.add_argument("--emulate", metavar="PDF", type=Path,
                     help="type onto an emulated typewriter and draw the sheets as a PDF")
    p.add_argument("--no-eject", action="store_true",
                   help="don't feed single sheets out after the last line")
    p.add_argument("--line-pause", type=float, metavar="S",
                   help="pause S seconds after each line (default from the profile)")
    p.add_argument("--paper", choices=["single_sheet", "continuous"],
                   help="paper handling (default from the profile)")
    p.add_argument("-y", "--yes", action="store_true", help="don't prompt for paper")


def _open(profile, a):
    from .transports import open_transport
    if getattr(a, "emulate", None):
        from .transports.emulator import Emulator
        return Emulator(profile, a.paper, getattr(a, "stock", None) or "letter")
    try:
        t = open_transport(profile, a.dry_run)
    except TransportError as e:
        sys.exit(f"daisywriter: {e}")
    st = t.status()
    if st is not None:
        print(f"{t.name}: {st.explain()} (status {st.raw:#04x})")
    return t


def _send(t, letters, profile, opts, a) -> int:
    from .job import PrintCancelled, print_letters
    ask = (lambda message: True) if a.yes else _ask
    try:
        done = print_letters(t, letters, profile, opts, ask)
    except PrintCancelled:
        print("cancelled")
        return 1
    except KeyboardInterrupt:
        print("\nstopped (the typewriter may finish the line it already has)")
        return 1
    except TransportError as e:
        print(f"daisywriter: {e}")
        return 1
    finally:
        t.close()
        if getattr(a, "emulate", None):
            _emulated(t, a)
    print(f"done: {len(done)} letter(s) sent" + (f" to {a.dry_run}" if a.dry_run else ""))
    return 0


def _emulated(t, a):
    from .pdf import write_pdf
    write_pdf(a.emulate, t.sheets, getattr(a, "stock", None) or "letter")
    print(f"wrote {a.emulate} ({len(t.sheets)} sheet(s))")
    for e in t.events:
        print(f"emulator: {e}")
    if not t.events:
        print("emulator: no problems (no firmware wraps, every sheet fed out)")


def _options(profile, a, top):
    from .job import PrintOptions
    return PrintOptions.for_profile(profile, top_lines=top, eject=not a.no_eject,
                                    line_pause_s=a.line_pause, paper=a.paper,
                                    stock=getattr(a, "stock", None))


def cmd_print(a) -> int:
    m = _run(a)
    letters = m.letters
    if a.letters:
        letters = [x for x in letters if x.number in a.letters]
        if not letters:
            sys.exit(f"daisywriter: no such letters (there are {len(m.letters)})")
    if not m.ok and not a.force:
        _print_issues(m, False)
        print("not printing because of the errors above (--force prints anyway)")
        return 1
    opts = _options(m.profile, a, a.top)
    t = _open(m.profile, a)
    return _send(t, letters, m.profile, opts, a)


def cmd_status(a) -> int:
    profile = load_profile(a.profile)
    a.dry_run = None
    t = _open(profile, a)
    t.close()
    return 0


def cmd_testpage(a) -> int:
    from .layout import Line, Page
    from .merge import Letter
    from .records import Record
    from .testpage import PAGES
    profile = load_profile(a.profile)
    lines: list[Line] = []
    for name in a.patterns:
        if lines:
            lines += [Line(), Line()]
        lines += PAGES[name](profile).lines
    letter = Letter(0, Record(0, {}), [], pages=[Page(1, lines)])
    opts = _options(profile, a, a.top)
    t = _open(profile, a)
    return _send(t, [letter], profile, opts, a)


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

    p = sub.add_parser("print", help="type the merged letters")
    _merge_args(p)
    _print_args(p, merge=True)
    p.add_argument("--letters", type=_letters_arg, help="letters to print, e.g. 1,3-5")
    p.add_argument("--force", action="store_true", help="print even if validation found errors")
    p.set_defaults(func=cmd_print)

    p = sub.add_parser("status", help="show whether the typewriter is connected and ready")
    p.add_argument("--profile", help="typewriter profile id or .toml path")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("testpage", help="type calibration patterns (margins, format, bold, charset)")
    p.add_argument("patterns", nargs="+", choices=["margins", "format", "bold", "charset"])
    _print_args(p, merge=False)
    p.set_defaults(func=cmd_testpage)

    p = sub.add_parser("gui", help="open the daisywriter window")
    p.set_defaults(func=lambda a: __import__("daisywriter.gui", fromlist=["main"]).main([]))

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
