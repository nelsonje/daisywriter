import pytest

from daisywriter.job import PrintCancelled, PrintOptions, print_letters
from daisywriter.layout import Cell, Line, Page
from daisywriter.merge import Letter
from daisywriter.profile import load_profile
from daisywriter.records import Record
from daisywriter.transports import WriteTimeout
from daisywriter.transports.fake import FakeTransport

PROFILE = load_profile("swintec-1146cmp")  # load offset 4, eject extra 3


def letter(n=1, pages=1, lines=3):
    return Letter(n, Record(n + 1, {}), [],
                  pages=[Page(p, [Line([Cell("x")]) for _ in range(lines)]) for p in range(1, pages + 1)])


def run(letters, ask=lambda m: True, **kw):
    t = FakeTransport()
    asked = []
    opts = PrintOptions.for_profile(PROFILE, **kw)

    def record_ask(message):
        asked.append(message)
        return ask(message)
    done = print_letters(t, letters, PROFILE, opts, record_ask, report=lambda s: None)
    return t, done, asked


def test_single_sheet_feeds_and_ejects():
    t, done, asked = run([letter()])
    assert done == [1]
    assert len(asked) == 1 and "rollers" in asked[0]
    # top margin 6 lines from the top edge, the sheet is loaded 4 lines down: feed 2
    assert t.writes[0] == b"\n\n"
    assert t.writes[1:4] == [b"x\n"] * 3
    # eject: 66 lines per page - (6 + 3) typed + 5 extra
    assert t.writes[4] == b"\n" * 62


def test_one_prompt_per_page():
    _, done, asked = run([letter(1, pages=2), letter(2)])
    assert done == [1, 2] and len(asked) == 3
    assert "letter 1, page 2 of 2" in asked[1]


def test_continuous_paper_uses_form_feed_and_no_prompts():
    t, _, asked = run([letter()], paper="continuous")
    assert asked == [] and t.writes[0] == b"\n" * 6 and t.writes[-1] == b"\x0c"


def test_no_eject():
    t, _, _ = run([letter()], eject=False)
    assert t.writes[-1] == b"x\n"


def test_cancel_at_the_paper_prompt():
    with pytest.raises(PrintCancelled):
        run([letter()], ask=lambda m: False)


def test_waits_while_off_line():
    t = FakeTransport()
    t.statuses = [0x08, 0x08, 0x18]  # off-line twice, then ready
    asked = []
    print_letters(t, [letter()], PROFILE, PrintOptions.for_profile(PROFILE),
                  lambda m: asked.append(m) or True, report=lambda s: None)
    assert sum("off-line" in m for m in asked) == 2


def test_timeout_sends_cancel_and_raises():
    t = FakeTransport()
    t.fail_after = 2
    with pytest.raises(WriteTimeout):
        print_letters(t, [letter()], PROFILE, PrintOptions.for_profile(PROFILE),
                      lambda m: True, report=lambda s: None)
    assert len(t.writes) == 2  # CAN couldn't be sent either: the connection is gone


def test_cancel_sends_can():
    t = FakeTransport()
    calls = iter([True, False])
    t.statuses = [0x08]  # off-line; the retry prompt then says no
    with pytest.raises(PrintCancelled):
        print_letters(t, [letter()], PROFILE, PrintOptions.for_profile(PROFILE),
                      lambda m: next(calls), report=lambda s: None)
    assert t.writes[-1] == b"\x18"


def test_stop_between_lines_and_progress():
    t = FakeTransport()
    seen = []
    with pytest.raises(PrintCancelled):
        print_letters(t, [letter(lines=5)], PROFILE, PrintOptions.for_profile(PROFILE), lambda m: True,
                      report=lambda s: None, stop=lambda: len(seen) >= 2,
                      progress=lambda *a: seen.append(a))
    assert seen == [(1, 1, 1, 5), (1, 1, 2, 5)]
    assert t.writes[-1] == b"\x18"  # CAN after stopping
