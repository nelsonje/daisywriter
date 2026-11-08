"""Find the letter body, where simulated typing errors are allowed.

Explicit {{body}} ... {{/body}} markers win. Without them the body is
auto-detected as the paragraphs between the salutation ("Dear ...,") and the
complimentary close ("Sincerely,"). If neither approach finds a body, no text
is body: errors are never spread over the whole letter by guesswork.
"""
from __future__ import annotations

import re

from . import issues as I
from .model import Align, Paragraph, Role, Span, Template

SALUTATION = re.compile(
    r"^(dear|to whom it may concern|hello|hi|greetings|gentlemen|ladies and gentlemen"
    r"|good (morning|afternoon|day))\b.*[,:]$", re.IGNORECASE)

CLOSINGS = [
    r"sincerely( yours)?", r"yours( very)? (truly|sincerely|faithfully)",
    r"very (truly|sincerely) yours", r"((best|kind|warm|warmest|kindest) )?regards",
    r"with (best|kind|warm) (regards|wishes)", r"best wishes", r"all the best",
    r"respectfully( yours| submitted)?", r"cordially( yours)?", r"thank you", r"thanks( again)?",
    r"gratefully( yours)?", r"faithfully( yours)?", r"cheers",
]
CLOSING = re.compile(r"^(" + "|".join(CLOSINGS) + r")\s*[,.!]?$", re.IGNORECASE)

SUBJECT_LINE = re.compile(r"^(re|subject|subj|ref|regarding|attn|attention)\s*:", re.IGNORECASE)

MAX_SALUTATION_WORDS = 12


def _visible(p: Paragraph) -> str:
    return " ".join(p.text.split())


def _all(p: Paragraph, attr: str) -> bool:
    spans = [s for s in p.spans if (s.text.strip() or s.field is not None)]
    return bool(spans) and all(getattr(s, attr) for s in spans)


def apply_regions(template: Template, closings: list[str] | None = None) -> Template:
    """Mark body spans and paragraph roles in place; return the template."""
    closing_re = CLOSING
    if closings:
        closing_re = re.compile(r"^(" + "|".join(CLOSINGS + closings) + r")\s*[,.!]?$", re.IGNORECASE)
    if any(s.marker for p in template.paragraphs for s in p.spans):
        _apply_markers(template)
    else:
        _auto_detect(template, closing_re)
    _mark_closing(template, closing_re)
    return template


def _apply_markers(template: Template):
    template.body_source = "markers"
    inside = False
    start_at = None
    kept = []
    for p in template.paragraphs:
        new_spans: list[Span] = []
        had_marker = False
        for s in p.spans:
            if s.marker == "body":
                had_marker = True
                if inside:
                    template.issues.append(I.error("{{body}} inside another {{body}}",
                                                   f"paragraph {p.index}"))
                inside, start_at = True, p.index
            elif s.marker == "/body":
                had_marker = True
                if not inside:
                    template.issues.append(I.error("{{/body}} without a matching {{body}}",
                                                   f"paragraph {p.index}"))
                inside = False
            else:
                s.body = inside
                new_spans.append(s)
        p.spans = new_spans
        if any(s.body for s in new_spans):
            p.role = Role.BODY
        # a marker on a line of its own disappears with its paragraph
        if had_marker and not "".join(s.text for s in new_spans).strip() and not any(
                s.field for s in new_spans):
            continue
        kept.append(p)
    if inside:
        template.issues.append(I.error("{{body}} is never closed with {{/body}}",
                                       f"paragraph {start_at}"))
    template.paragraphs = kept
    body = [p.index for p in kept if p.role is Role.BODY]
    template.issues.append(I.info(f"letter body: {_ranges(body)} (from {{{{body}}}} markers)"
                                  if body else "the {{body}} markers enclose no text", "template"))


def _auto_detect(template: Template, closing_re):
    paras = template.paragraphs
    sal = next((i for i, p in enumerate(paras)
                if SALUTATION.match(_visible(p)) and len(_visible(p).split()) <= MAX_SALUTATION_WORDS),
               None)
    close = None
    if sal is not None:
        close = next((i for i in range(sal + 1, len(paras)) if closing_re.match(_visible(paras[i]))),
                     None)
    if sal is None or close is None:
        template.body_source = "none"
        missing = "salutation (Dear ...,)" if sal is None else "closing (Sincerely, ...)"
        template.issues.append(I.warning(
            f"couldn't find the letter body (no {missing}); typing errors stay off unless you "
            "add {{body}} ... {{/body}} markers", "template"))
        return
    template.body_source = "auto"
    paras[sal].role = Role.SALUTATION
    body = []
    for p in paras[sal + 1:close]:
        text = _visible(p)
        if (not text or SUBJECT_LINE.match(text) or p.align is Align.CENTER
                or _all(p, "bold") or _all(p, "underline")):
            continue
        p.role = Role.BODY
        for s in p.spans:
            s.body = True
        body.append(p.index)
    template.issues.append(I.info(
        f"letter body: {_ranges(body)} (auto-detected between "
        f"\"{_visible(paras[sal])}\" and \"{_visible(paras[close])}\")"
        if body else "no body paragraphs between the salutation and the closing", "template"))


def _mark_closing(template: Template, closing_re):
    """The complimentary close and everything after it form the signature block."""
    paras = template.paragraphs
    idx = None
    for i, p in enumerate(paras):
        if p.role is Role.BODY:
            idx = None  # the closing must come after the last body paragraph
        elif idx is None and closing_re.match(_visible(p)):
            idx = i
    if idx is None:
        return
    for p in paras[idx:]:
        if p.role is not Role.BODY:
            p.role = Role.CLOSING


def _ranges(indexes: list[int]) -> str:
    if not indexes:
        return "none"
    parts, start, prev = [], indexes[0], indexes[0]
    for i in indexes[1:] + [None]:
        if i is not None and i == prev + 1:
            prev = i
            continue
        parts.append(f"{start}" if start == prev else f"{start}–{prev}")
        if i is not None:
            start = prev = i
    word = "paragraph" if len(indexes) == 1 else "paragraphs"
    return f"{word} {', '.join(parts)}"
