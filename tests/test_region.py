from daisywriter.model import Align, Paragraph, Role, Span, Template
from daisywriter.region import apply_regions


def letter(*texts, props=None):
    paras = []
    for i, t in enumerate(texts, start=1):
        spans = []
        for part in t.split("|"):
            if part in ("{{body}}", "{{/body}}"):
                spans.append(Span(marker=part.strip("{}")))
            else:
                spans.append(Span(part))
        paras.append(Paragraph(spans, i, **(props or {}).get(i, {})))
    return apply_regions(Template("t.docx", paras))


def body(t):
    return [p.text for p in t.paragraphs if p.role is Role.BODY]


def test_block_letter():
    t = letter("June 1, 2026", "", "Ms. Ada Smith", "", "Dear Ms. Smith:", "",
               "First paragraph.", "", "Second paragraph.", "", "Sincerely,", "", "", "Bob", "Enc.")
    assert t.body_source == "auto"
    assert body(t) == ["First paragraph.", "Second paragraph."]
    assert [p.text for p in t.paragraphs if p.role is Role.CLOSING][:1] == ["Sincerely,"]
    assert t.paragraphs[13].role is Role.CLOSING  # the signature line
    assert all(s.body for p in t.paragraphs if p.role is Role.BODY for s in p.spans)


def test_subject_heading_and_bold_lines_are_excluded():
    t = letter("Dear Team,", "Re: budget", "SUMMARY", "Body text here.", "Best regards,",
               props={3: {"align": Align.CENTER}})
    assert body(t) == ["Body text here."]


def test_long_sentence_starting_with_dear_isnt_a_salutation():
    t = letter("Dear me, this is a very long first sentence that goes on and on and on and on, sadly,",
               "Text.", "Sincerely,")
    assert t.body_source == "none" and body(t) == []


def test_no_closing_means_no_body():
    t = letter("Dear Sam,", "Text.", "Love, Mom")
    assert t.body_source == "none" and body(t) == []
    assert any("couldn't find the letter body" in i.message for i in t.issues)


def test_ps_after_signature_is_not_body():
    t = letter("Dear Sam,", "Text.", "Yours truly,", "Ann", "P.S. Bring snacks.")
    assert body(t) == ["Text."]
    assert t.paragraphs[4].role is Role.CLOSING


def test_markers_override_auto_detection():
    t = letter("Dear Sam,", "{{body}}", "Only this.", "{{/body}}", "Not this.", "Sincerely,")
    assert t.body_source == "markers"
    assert body(t) == ["Only this."]
    assert [p.text for p in t.paragraphs] == ["Dear Sam,", "Only this.", "Not this.", "Sincerely,"]


def test_inline_markers():
    t = letter("Intro |{{body}}|typo zone|{{/body}}| outro")
    spans = t.paragraphs[0].spans
    assert [(s.text, s.body) for s in spans] == [("Intro ", False), ("typo zone", True),
                                                  (" outro", False)]


def test_unbalanced_markers():
    t = letter("|{{body}}|", "x", "|{{body}}|", "y")
    assert any("inside another" in i.message for i in t.issues)
    assert any("never closed" in i.message for i in t.issues)
