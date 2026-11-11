"""Document model shared by template parsing, merging and layout."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Align(Enum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    JUSTIFY = "justify"


class Role(Enum):
    OTHER = "other"
    SALUTATION = "salutation"
    BODY = "body"
    CLOSING = "closing"  # the complimentary close and everything after it


@dataclass(frozen=True)
class FieldRef:
    """A merge field in the template.

    picture is a Word-style format picture (date or number). kind is "date" or
    "number" when a Word switch (\\@ or \\#) says which, or None when it is
    decided by the value (placeholders). source is "mergefield", "placeholder"
    or "date" (a Word DATE field, i.e. today's date).
    """
    name: str
    picture: str | None = None
    kind: str | None = None
    case: str | None = None  # "upper" | "lower" | "caps" | "firstcap"
    before: str = ""  # Word \b: text placed before a non-empty value
    after: str = ""  # Word \f: text placed after a non-empty value
    source: str = "placeholder"

    @property
    def label(self) -> str:
        return f"«{self.name}»"


@dataclass
class Span:
    """A run of text with uniform formatting, or a merge field, or a body marker.

    Text may contain "\\t" (tab), "\\n" (forced line break) and "\\f" (page break).
    """
    text: str = ""
    bold: bool = False
    underline: bool = False
    field: FieldRef | None = None
    marker: str | None = None  # "body" or "/body"
    body: bool = False  # inside the letter body: typing errors allowed
    from_field: bool = False  # after merging: text came from a field value
    strike: bool = False  # strikethrough
    over: str = ""  # typing-error correction struck over each character (errors.py)


@dataclass
class Paragraph:
    spans: list[Span]
    index: int  # 1-based position in the template, for messages
    align: Align = Align.LEFT
    left_pt: float = 0.0
    right_pt: float = 0.0
    first_line_pt: float = 0.0  # relative to left_pt; negative is a hanging indent
    space_before_pt: float = 0.0
    space_after_pt: float = 0.0
    keep_with_next: bool = False
    page_break_before: bool = False
    contextual_spacing: bool = False
    style: str | None = None
    tab_stops_pt: tuple[float, ...] = ()
    default_tab_pt: float = 36.0  # Word's default tab interval (Options > Default tab stops)
    role: Role = Role.OTHER

    @property
    def text(self) -> str:
        """Visible text, with fields shown as «Name» and markers as {{body}}."""
        out = []
        for s in self.spans:
            if s.field is not None:
                out.append(s.field.label)
            elif s.marker is not None:
                out.append("{{" + s.marker + "}}")
            else:
                out.append(s.text)
        return "".join(out)

    def copy_with(self, spans: list[Span]) -> Paragraph:
        p = Paragraph(**{**self.__dict__, "spans": spans})
        return p


@dataclass
class Template:
    path: str
    paragraphs: list[Paragraph]
    issues: list = field(default_factory=list)
    body_source: str = "none"  # "markers" | "auto" | "none"

    def fields(self) -> list[FieldRef]:
        """Merge fields that need a data column, in order of first use."""
        seen, out = set(), []
        for p in self.paragraphs:
            for s in p.spans:
                f = s.field
                if f is not None and f.source != "date" and f.name not in seen:
                    seen.add(f.name)
                    out.append(f)
        return out
