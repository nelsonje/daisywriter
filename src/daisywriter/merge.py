"""Fill a template with one record's values."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field, replace

from . import issues as I
from .layout import Page
from .model import FieldRef, Paragraph, Span, Template
from .profile import Profile
from .records import DataSet, Record, normalize
from .template import split_placeholders
from .values import DEFAULT_DATE, format_value


@dataclass
class MergeSettings:
    today: dt.date = field(default_factory=dt.date.today)
    default_date: str = DEFAULT_DATE  # for {{Today}}, and values Excel shows as General
    excel_formats: bool = True  # show values as formatted in Excel unless the template says otherwise


@dataclass
class Letter:
    number: int  # 1-based position in the merge
    record: Record
    paragraphs: list[Paragraph]
    issues: list[I.Issue] = field(default_factory=list)
    page_number_text: str | None = None
    pages: list[Page] = field(default_factory=list)

    def summary(self, fields: list[str] | None = None) -> str:
        """A short description, from the given columns or the first non-empty values."""
        vals = self.record.values
        keys = fields or list(vals)[:2]
        return " ".join(str(vals[k]).strip() for k in keys if vals.get(k) not in (None, ""))


def resolve(ref: FieldRef, record: Record, dataset: DataSet,
            settings: MergeSettings) -> tuple[str | None, str | None]:
    """Return (text, problem). text is None when the field has no data column."""
    if ref.source == "date":
        return format_value(settings.today, ref, settings.default_date)
    header = dataset.header_for(ref.name)
    if header is None:
        if normalize(ref.name) == "today":
            return format_value(settings.today, ref, settings.default_date)
        return None, None
    excel_format = record.formats.get(header) if settings.excel_formats else None
    return format_value(record.values.get(header), ref, settings.default_date, excel_format)


def merge_text(text: str, record: Record, dataset: DataSet, settings: MergeSettings) -> str:
    """Fill placeholders in a plain string (used for the page-number format)."""
    out = []
    for s in split_placeholders([Span(text)]):
        if s.field is not None:
            value, _ = resolve(s.field, record, dataset, settings)
            out.append(s.field.label if value is None else value)
        else:
            out.append(s.text)
    return "".join(out)


def drop_blank_lines(items) -> tuple[list[Span] | None, list[str], list[str]]:
    """Leave out lines made only of blank fields, like an empty Address2.

    items are (span, field name or None, blank field?). A line ends at a manual
    line break or the end of the paragraph. Returns (spans, or None when the
    whole paragraph goes; names of fields on dropped lines; other blank fields).
    """
    lines: list[list] = [[]]
    for span, name, is_blank in items:
        for k, part in enumerate(span.text.split("\n")):
            if k:
                lines.append([])
            lines[-1].append((replace(span, text=part), name if k == 0 else None, is_blank and k == 0))

    def droppable(line) -> bool:
        return (any(b for _, _, b in line) and not any(n and not b for _, n, b in line)
                and not "".join(s.text for s, _, _ in line).strip())

    kept = [ln for ln in lines if not droppable(ln)]
    gone = [n for ln in lines if droppable(ln) for _, n, _ in ln if n]
    empty = [n for ln in kept for _, n, b in ln if b]
    if not kept:
        return None, gone, empty
    spans: list[Span] = []
    for k, line in enumerate(kept):
        if k:
            spans.append(Span("\n", body=spans[-1].body if spans else False))
        spans += [s for s, _, _ in line if s.text]
    return spans, gone, empty


def merge_letter(number: int, template: Template, record: Record, dataset: DataSet,
                 profile: Profile, settings: MergeSettings) -> Letter:
    where = f"letter {number} (row {record.row})"
    issues: list[I.Issue] = []
    substituted: dict[str, str] = {}
    missing: dict[str, set[str]] = {}
    blank: list[str] = []  # blank fields inside other text
    dropped: list[str] = []  # blank fields whose whole line is left out
    paragraphs = []

    for p in template.paragraphs:
        items = []  # (merged span, field name or None, blank field?)
        for s in p.spans:
            if s.field is not None:
                value, problem = resolve(s.field, record, dataset, settings)
                if problem:
                    issues.append(I.warning(f"{s.field.label}: {problem}", where, number))
                if value is None:  # unknown column, reported once by validation
                    items.append((Span(s.field.label, s.bold, s.underline, body=s.body,
                                       from_field=True), s.field.name, False))
                    continue
                text, subs, miss = profile.typeable(value)
                place = s.field.label
                items.append((Span(text, s.bold, s.underline, body=s.body, from_field=True),
                              s.field.name, not value.strip()))
            else:
                text, subs, miss = profile.typeable(s.text)
                place = f"paragraph {p.index}"
                items.append((Span(text, s.bold, s.underline, body=s.body), None, False))
            substituted.update(subs)
            for ch in miss:
                missing.setdefault(ch, set()).add(place)
        spans, gone, empty = drop_blank_lines(items)
        dropped += gone
        blank += empty
        if spans is not None:
            paragraphs.append(p.copy_with(spans))

    for name in dict.fromkeys(blank):
        issues.append(I.warning(f"«{name}» is blank", where, number))
    for name in dict.fromkeys(dropped):
        issues.append(I.info(f"«{name}» is blank, so its line is left out", where, number))
    for ch, rep in substituted.items():
        issues.append(I.warning(f"\"{ch}\" isn't on the printwheel and is typed as \"{rep}\"",
                                where, number))
    for ch, places in missing.items():
        issues.append(I.error(
            f"\"{ch}\" (U+{ord(ch):04X}) can't be typed on the {profile.name} "
            f"(in {', '.join(sorted(places))})", where, number))
    return Letter(number, record, paragraphs, issues)
