"""The firmware model, and every golden letter typed through it.

The round trip renders letters to bytes, sends them through the print job to
the emulator, and checks that each sheet holds exactly what the layout says:
every character, re-strike, underscore and hyphen at its line and column, no
firmware wrap, and every sheet fed out past the rollers.
"""
import dataclasses
from collections import Counter
from pathlib import Path

import pytest
from test_golden import long_letter

from daisywriter.job import PrintOptions, print_letters
from daisywriter.layout import Cell, Line, Page, PageNumbers
from daisywriter.merge import Letter
from daisywriter.pdf import write_pdf
from daisywriter.pipeline import run
from daisywriter.profile import builtin_profiles, load_profile
from daisywriter.records import Record
from daisywriter.render import bold_restrikes, render_line
from daisywriter.transports.emulator import Emulator

HERE = Path(__file__).parent
SWINTEC = load_profile("swintec-1146cmp")
OLYMPIA = load_profile("olympia-electronic-compact-2")


def typed(data: bytes, profile=SWINTEC) -> Emulator:
    e = Emulator(profile)
    e.load_sheet()
    e.write(data)
    return e


def row(e: Emulator, line: int = 4) -> dict[int, list[str]]:
    """Strikes on one line (6 lpi lines below the top edge), by column."""
    return {c: chars for (r, c), chars in e.sheet.grid().items() if r == line}


def test_text_waits_for_a_control_code():
    e = typed(b"ab")
    assert e.sheet.strikes == []
    e.write(b"\r")
    assert row(e) == {10: ["a"], 11: ["b"]}


def test_cr_overprints_and_lf_returns():
    e = typed(b"ab\r_\ncd\n")
    assert row(e) == {10: ["a", "_"], 11: ["b"]}
    assert row(e, 5) == {10: ["c"], 11: ["d"]}


def test_backspace_strikes_from_the_right():
    e = typed(b"abc\r  c\x08\x08b\n")
    strikes = [(s.ch, s.from_right) for s in e.sheet.strikes]
    # the re-strike of c follows the carrier back from column 13; b is reached from c+1
    assert strikes == [("a", False), ("b", False), ("c", False), ("c", True), ("b", True)]


def test_auto_wrap_past_the_right_margin():
    e = typed(b"x" * 67 + b"\n")
    assert len(row(e)) == 66 and row(e, 5) == {10: ["x"]}
    assert any("wrapped the line at column 76" in m for m in e.events)


def test_cancel_discards_and_leftovers_are_reported():
    e = typed(b"gone\x18kept\n")
    assert "".join(c[0] for _, c in sorted(row(e).items())) == "kept"
    e.write(b"stuck")
    e.close()
    assert any("never typed" in m for m in e.events)


def test_shift_out_petals_on_the_olympia():
    e = typed(b"a\x0e-/\x0fb\n", OLYMPIA)
    assert [chars[0] for _, chars in sorted(row(e).items())] == ["a", "©", "®", "b"]
    assert e.events == []
    # spaces before SO are typed only if the firmware keeps the column pointer
    e = typed(b"a \x0e-\x0f\n", OLYMPIA)
    assert any("spaces just before SO" in m for m in e.events)


def test_eject_needs_to_clear_the_rollers():
    page = Page(1, [Line([Cell("x")])])

    def sheets_after(extra):
        profile = dataclasses.replace(SWINTEC, eject_extra_lines=extra)
        e = Emulator(profile)
        letters = [Letter(n, Record(n, {}), [], pages=[page]) for n in (1, 2)]
        print_letters(e, letters, profile, PrintOptions.for_profile(profile), lambda m: True, lambda s: None)
        return e

    # 2026-11-10 on the Swintec: 3 extra lines left the edge of the sheet in the rollers
    assert any("still held" in m for m in sheets_after(3).events)
    e = sheets_after(5)
    assert e.events == [] and len(e.sheets) == 2 and all(s.out for s in e.sheets)


def test_continuous_paper_pages_by_form_feed():
    e = Emulator(SWINTEC, paper="continuous")
    e.write(b"\n" * 6 + b"one\n\x0c" + b"\n" * 6 + b"two\n\x0c")
    assert [len(s.strikes) for s in e.sheets] == [3, 3, 0]
    assert e.sheets[1].grid()[(6, 10)] == ["t"]


def expected_strikes(line: Line, profile) -> Counter:
    """What the layout says each column of a line should receive."""
    want = Counter()
    restrikes = len(bold_restrikes(profile))
    mark = profile.raw.get("strikethrough", "-")
    for k, c in enumerate(line.cells):
        col = profile.margin_left + k
        if c.ch != " ":
            want[(col, c.ch)] += 1 + (restrikes if c.bold else 0)
        if c.underline:
            want[(col, "_")] += 1
        if c.strike:
            want[(col, mark)] += 1
        for ch in c.over:  # typing-error corrections
            want[(col, ch)] += 1
    return want


def round_trip(m, top=6):
    e = Emulator(m.profile)
    opts = PrintOptions.for_profile(m.profile, top_lines=top)
    print_letters(e, m.letters, m.profile, opts, lambda msg: True, lambda s: None)
    e.close()
    assert e.events == []
    pages = [p for letter in m.letters for p in letter.pages]
    assert len(e.sheets) == len(pages) and all(s.out for s in e.sheets)
    for sheet, page in zip(e.sheets, pages, strict=True):
        grid = sheet.grid()
        got = Counter()
        for (r, col), chars in grid.items():
            for ch in chars:
                got[(r, col, ch)] += 1
        want = Counter()
        for i, line in enumerate(page.lines):
            for (col, ch), n in expected_strikes(line, m.profile).items():
                want[(top + i, col, ch)] += n
        assert got == want, f"sheet {sheet.number} differs from the layout"
    return e


def test_round_trip_word_template(sample_dir, settings):
    m = run(HERE / "fixtures" / "word-letter.docx", sample_dir / "letter-data.xlsx", settings)
    e = round_trip(m)
    assert any(s.from_right for s in e.sheets[0].strikes)  # bold re-struck right to left


def test_round_trip_generated_template(sample_dir, settings):
    round_trip(run(sample_dir / "letter-template.docx", sample_dir / "letter-data.xlsx", settings))


def test_round_trip_with_typing_errors(sample_dir, settings):
    from daisywriter.errors import ErrorSettings
    settings.errors = ErrorSettings(enabled=True, rate=20)
    m = run(HERE / "fixtures" / "word-letter.docx", sample_dir / "letter-data.xlsx", settings)
    assert all(x.typing_errors for x in m.letters)
    e = round_trip(m)
    assert any(st.ch == "x" for st in e.sheets[0].strikes)


def test_round_trip_multi_page(sample_dir, settings, tmp_path):
    settings.layout.page_numbers = PageNumbers("after_first", "top", "left", "Page {page}")
    m = run(long_letter(tmp_path / "long.docx"), sample_dir / "letter-data.xlsx", settings)
    m.letters = m.letters[:1]
    assert len(m.letters[0].pages) > 1
    round_trip(m)


@pytest.mark.parametrize("profile", [SWINTEC, OLYMPIA], ids=["swintec", "olympia"])
def test_round_trip_formatting(profile):
    cells = ([Cell(ch) for ch in "plain "] + [Cell(ch, bold=True) for ch in "bold"]
             + [Cell(" ")] + [Cell(ch, underline=True) for ch in "under line"]
             + [Cell(" ")] + [Cell(ch, bold=True, underline=True, strike=True) for ch in "all"])
    line = Line(cells)
    e = typed(render_line(line, profile), profile)
    got = Counter((c, ch) for c, chars in row(e).items() for ch in chars)
    assert got == expected_strikes(line, profile)


def test_pdf(tmp_path):
    e = typed(b"Hello (world)\n")
    path = tmp_path / "out.pdf"
    write_pdf(path, e.sheets)
    data = path.read_bytes()
    assert data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")
    assert b"/Count 1" in data and b"(\\()" in data and b"(H)" in data


@pytest.mark.parametrize("profile", list(builtin_profiles().values()), ids=lambda p: p.id)
@pytest.mark.parametrize("name", ["format", "bold", "charset"])
def test_test_pages_fit_and_name_every_character(profile, name):
    """Only the margin probe may reach the firmware's wrap, and every byte a test
    page sends is a character the profile describes."""
    from daisywriter.testpage import PAGES
    e = Emulator(profile)
    e.load_sheet()
    for line in PAGES[name](profile).lines:
        e.write(render_line(line, profile))
    problems = [ev for ev in e.events if "wrapped" in ev or "doesn't describe" in ev]
    assert problems == []


def test_question_mark_is_an_ordinary_character():
    e = typed(b"Why?\n", OLYMPIA)
    assert not [ev for ev in e.events if "doesn't describe" in ev]
    assert "?" in [ch for chars in row(e).values() for ch in chars]


@pytest.mark.parametrize("profile", list(builtin_profiles().values()), ids=lambda p: p.id)
def test_special_characters_round_trip(profile):
    """Each mapped character, typed through the firmware model, lands as itself."""
    text = "".join(profile.charset)
    e = Emulator(profile)
    e.load_sheet()
    e.write(render_line(Line([Cell(ch) for ch in text]), profile))
    line = max(r for (r, _c) in e.sheet.grid())
    got = "".join(chars[0] for _c, chars in sorted(row(e, line).items()))
    assert got == text
    assert not [ev for ev in e.events if "doesn't describe" in ev]


def test_swintec_firmwares_differ_where_the_notes_say():
    cmp_, cm = load_profile("swintec-1146cmp"), load_profile("swintec-1146cm-3z28")
    assert cmp_.charset.get("|") is None and cmp_.can_type("|")  # 335-U: | is a bar
    assert cm.charset["|"] == b"," and cm.charset["¶"] == b"|"  # 3Z28: | prints ¶
    assert cmp_.charset["£"] == b"*" and cm.charset["£"] == b"}"
