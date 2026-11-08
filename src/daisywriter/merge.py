"""Fill a template with one record's values."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

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
    default_date: str = DEFAULT_DATE


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
    return format_value(record.values.get(header), ref, settings.default_date)


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
        spans = []
        fields_here, blank_here = 0, 0
        for s in p.spans:
            if s.field is not None:
                fields_here += 1
                value, problem = resolve(s.field, record, dataset, settings)
                if problem:
                    issues.append(I.warning(f"{s.field.label}: {problem}", where, number))
                if value is None:  # unknown column, reported once by validation
                    spans.append(Span(s.field.label, s.bold, s.underline, body=s.body,
                                      from_field=True))
                    continue
                if not value.strip():
                    blank_here += 1
                text, subs, miss = profile.typeable(value)
                place = s.field.label
                spans.append(Span(text, s.bold, s.underline, body=s.body, from_field=True))
            else:
                text, subs, miss = profile.typeable(s.text)
                place = f"paragraph {p.index}"
                spans.append(Span(text, s.bold, s.underline, body=s.body))
            substituted.update(subs)
            for ch in miss:
                missing.setdefault(ch, set()).add(place)
        # a line made only of blank fields (an empty Address2, say) is left out
        if fields_here and blank_here == fields_here and not "".join(
                sp.text for sp in spans).strip():
            dropped += [s.field.name for s in p.spans if s.field is not None]
            continue
        blank += [s.field.name for s, new in zip(p.spans, spans)
                  if s.field is not None and not new.text.strip()]
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
