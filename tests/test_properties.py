"""Property tests: rules that must hold for any text and any block sizes."""
from hypothesis import given, settings
from hypothesis import strategies as st

from daisywriter.layout import Cell, LayoutSettings, Line, _Block, paginate, wrap_paragraph
from daisywriter.model import Align, Paragraph, Span
from daisywriter.profile import load_profile

PROFILE = load_profile("swintec-1146cmp")

word = st.text(alphabet="abcdefghijklmnopqrstuvwxyzABC0123456789.,;:'!?-", min_size=1, max_size=18)
space = st.sampled_from([" ", " ", " ", "  ", "\n", "\t"])


@st.composite
def paragraphs(draw):
    words = draw(st.lists(word, min_size=1, max_size=80))
    text = words[0] + "".join(draw(space) + w for w in words[1:])
    spans, i = [], 0
    while i < len(text):  # random formatting runs
        n = draw(st.integers(1, 30))
        spans.append(Span(text[i:i + n], bold=draw(st.booleans()), underline=draw(st.booleans())))
        i += n
    return Paragraph(
        spans, 1,
        align=draw(st.sampled_from(list(Align))),
        left_pt=draw(st.sampled_from([0, 36, 72])),
        right_pt=draw(st.sampled_from([0, 36])),
        first_line_pt=draw(st.sampled_from([0, 36, -36])),
    )


def nonspace(s: str) -> str:
    return "".join(s.split())


@settings(max_examples=300, deadline=None)
@given(paragraphs(), st.booleans())
def test_wrap_rules(p, justify):
    issues = []
    out = wrap_paragraph(p, PROFILE, LayoutSettings(justify=justify), issues, "")
    end_col = PROFILE.line_width - PROFILE.pt_to_cols(p.right_pt)
    text = "".join(s.text for s in p.spans)
    # nothing lost, added or reordered
    assert nonspace("".join(ln.text for ln, _ in out)) == nonspace(text)
    for ln, end in out:
        # never wider than the margins, and never a trailing space to type
        assert len(ln.cells) <= end_col
        assert not ln.text.endswith(" ")
    # each character keeps its formatting
    fmt = [(c, s.bold, s.underline) for s in p.spans for c in s.text if not c.isspace()]
    got = [(c.ch, c.bold, c.underline) for ln, _ in out for c in ln.cells if not c.ch.isspace()]
    assert got == fmt
    if p.align is Align.JUSTIFY and justify:
        for ln, end in out:
            words = ln.text.split()
            if end == "wrap" and len(words) > 1 and "\t" not in text and not issues:
                assert len(ln.cells) == end_col


blocks = st.lists(st.tuples(st.integers(1, 8), st.integers(0, 2), st.booleans()), min_size=1,
                  max_size=25)


@settings(max_examples=300, deadline=None)
@given(blocks, st.integers(10, 30))
def test_pagination_rules(spec, capacity):
    bl = [_Block([Line([Cell(chr(65 + k % 26))], para=k) for _ in range(n)], gap, keep)
          for k, (n, gap, keep) in enumerate(spec)]
    pages = paginate(bl, lambda page: capacity)
    placed = [ln.para for page in pages for ln in page if ln.cells]
    # every line placed once, in order
    assert placed == [k for k, (n, _, _) in enumerate(spec) for _ in range(n)]
    for page in pages:
        assert len(page) <= capacity
        assert page[0].cells  # no page starts with a blank line
    # a block that splits leaves at least 2 lines on each page; short blocks never split
    for k, (n, _, _) in enumerate(spec):
        parts = [sum(1 for ln in page if ln.para == k and ln.cells) for page in pages]
        parts = [x for x in parts if x]
        if len(parts) > 1:
            assert n >= 4 and min(parts) >= 2
