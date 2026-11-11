import datetime as dt
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from daisywriter.errors import NEIGHBOURS, ErrorSettings, add_typing_errors, intended_text, seed_for
from daisywriter.merge import MergeSettings
from daisywriter.model import Paragraph, Span
from daisywriter.pipeline import Settings, run

HERE = Path(__file__).parent
TEXT = ("We are pleased to tell you that the machine has been inspected, cleaned, and adjusted "
        "in our shop, and that it left here today by parcel post. Please note that the machine "
        "comes with a fabric ribbon; carbon film ribbons are not compatible with this model.")
ALWAYS = ErrorSettings(enabled=True, rate=100, min_gap=0)


def para(*spans, index=1):
    return Paragraph(list(spans), index)


def body(text, **kw):
    return Span(text, body=True, **kw)


def test_neighbours_are_mutual():
    assert set(NEIGHBOURS["e"]) == set("wrsd")
    assert all(a in NEIGHBOURS[b] for a in NEIGHBOURS for b in NEIGHBOURS[a])


def test_reproducible_from_the_seed():
    one = add_typing_errors([para(body(TEXT))], ALWAYS, 7)
    assert one == add_typing_errors([para(body(TEXT))], ALWAYS, 7)
    assert one != add_typing_errors([para(body(TEXT))], ALWAYS, 8)


def test_only_in_typed_body_text_between_the_first_and_last_words():
    spans = [body("Thank you "), Span("for your letter of "), body("Ann Smith", from_field=True),
             body(" " + TEXT)]
    (p,), made = add_typing_errors([para(*spans)], ALWAYS, 1)
    assert made
    assert p.spans[0].text.startswith("Thank") and not p.spans[0].over  # the first word
    assert spans[1] in p.spans  # not body
    assert any(s.text == "Ann Smith" and not s.over for s in p.spans)  # field value untouched
    assert p.spans[-1].text.endswith("model.")  # last word untouched
    assert intended_text(p.spans) == "".join(s.text for s in spans)


def test_corrections_by_style():
    (p,), made = add_typing_errors([para(body(TEXT))], ErrorSettings(True, 100, "overstrike", min_gap=0), 3)
    over = [s for s in p.spans if s.over]
    for e in made:
        assert e.style == ("overstrike" if e.kind == "substitution" else "xout")
    assert any(len(s.text) == 1 and s.over.isalpha() and s.over != "x" for s in over)
    (p,), made = add_typing_errors([para(body(TEXT))], ErrorSettings(True, 100, "xout", min_gap=0), 3)
    assert {e.style for e in made} == {"xout"}
    assert all(s.over == "x" for s in p.spans if s.over)


def test_rate_and_spacing():
    assert add_typing_errors([para(body(TEXT))], ErrorSettings(True, 0), 1)[1] == []
    _, made = add_typing_errors([para(body(TEXT))], ErrorSettings(True, 100, min_gap=5), 1)
    assert 2 <= len(made) <= len(TEXT.split()) // 6 + 1


@settings(max_examples=150, deadline=None)
@given(words=st.lists(st.text("abcdefghijklmnopqrstuvwxyzABC", min_size=1, max_size=9), min_size=1, max_size=40),
       seed=st.integers(0, 2**32), style=st.sampled_from(["mix", "xout", "overstrike"]))
def test_reading_through_the_corrections_gives_the_text(words, seed, style):
    text = " ".join(words) + "."
    (p,), _ = add_typing_errors([para(body(text))], ErrorSettings(True, 60, style, min_gap=1), seed)
    assert intended_text(p.spans) == text
    for s in p.spans:
        assert not s.over or s.over == "x" or len(s.text) == 1


def test_pipeline_seeds(sample_dir):
    def letters(**kw):
        s = Settings(merge=MergeSettings(today=dt.date(2026, 11, 8)),
                     errors=ErrorSettings(enabled=True, rate=10, **kw))
        return run(HERE / "fixtures" / "word-letter.docx", sample_dir / "letter-data.xlsx", s).letters

    base = letters()
    assert all(x.typing_errors for x in base)
    assert [x.paragraphs for x in letters()] == [x.paragraphs for x in base]
    assert [x.paragraphs for x in letters(salt=1)] != [x.paragraphs for x in base]
    from daisywriter.session import letter_key
    key = letter_key(HERE / "fixtures" / "word-letter.docx", base[1])
    rerolled = letters(letter_salts={key: 1})
    assert rerolled[0].paragraphs == base[0].paragraphs and rerolled[1].paragraphs != base[1].paragraphs
    assert seed_for(key, ErrorSettings()) != seed_for(key, ErrorSettings(salt=1))
    assert any("typing errors:" in i.message for i in base[0].issues)


def test_no_body_warns(tmp_path, sample_dir):
    import docx
    d = docx.Document()
    d.add_paragraph("Hello {{FirstName}}")
    d.save(str(tmp_path / "t.docx"))
    s = Settings(errors=ErrorSettings(enabled=True))
    m = run(tmp_path / "t.docx", sample_dir / "letter-data.xlsx", s)
    assert any("letter body wasn't found" in i.message for i in m.issues)
    assert not any(x.typing_errors for x in m.letters)
