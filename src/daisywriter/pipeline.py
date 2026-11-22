"""Run the whole merge: template + data + profile -> validated, laid-out letters."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import issues as I
from .errors import ErrorSettings, add_typing_errors, seed_for
from .frame import Frame, fit_page
from .layout import LayoutSettings, layout_letter
from .merge import Letter, MergeSettings, merge_letter, merge_text
from .model import Template
from .profile import Profile, load_profile
from .records import DataSet, load_records, normalize
from .region import apply_regions
from .session import letter_key
from .template import load_template


@dataclass
class Settings:
    profile: str | None = None  # built-in id or path to a .toml
    sheet: str | None = None
    merge: MergeSettings = field(default_factory=MergeSettings)
    layout: LayoutSettings = field(default_factory=LayoutSettings)
    closings: list[str] = field(default_factory=list)  # extra complimentary closes (regexes)
    errors: ErrorSettings = field(default_factory=ErrorSettings)


@dataclass
class Merge:
    template: Template
    dataset: DataSet
    profile: Profile
    settings: Settings
    letters: list[Letter]
    issues: list[I.Issue]  # template, data and cross-checks; letters carry their own
    frame: Frame = field(default_factory=Frame)  # paper and margins

    def all_issues(self) -> list[I.Issue]:
        return self.issues + [i for letter in self.letters for i in letter.issues]

    @property
    def ok(self) -> bool:
        return not I.has_errors(self.all_issues())


def check_fields(template: Template, dataset: DataSet) -> list[I.Issue]:
    issues = []
    used = set()
    for ref in template.fields():
        header = dataset.header_for(ref.name)
        if header is None:
            if normalize(ref.name) == "today":
                continue
            hint = dataset.suggest(ref.name)
            hint = f"; did you mean \"{hint}\"?" if hint else ""
            issues.append(I.error(f"{ref.label} has no matching column in the spreadsheet{hint}",
                                  "template"))
        else:
            used.add(header)
    unused = [h for h in dataset.headers if h not in used]
    if unused and dataset.headers:
        issues.append(I.info(f"columns not used by the template: {', '.join(unused)}", "data"))
    return issues


def run(template_path: str | Path, data_path: str | Path, settings: Settings | None = None) -> Merge:
    settings = settings or Settings()
    profile = load_profile(settings.profile)
    template = apply_regions(load_template(template_path), settings.closings)
    dataset = load_records(data_path, settings.sheet)
    issues = list(template.issues) + list(dataset.issues)
    issues += check_fields(template, dataset)
    lay = settings.layout
    frame, page_issues = fit_page(template.page, profile, lay.stock, lay.top_lines, lay.bottom_lines)
    issues.append(I.info(frame.describe(profile), "page setup"))
    issues += page_issues
    has_body = any(s.body for p in template.paragraphs for s in p.spans)
    if settings.errors.enabled and not has_body:
        issues.append(I.warning("typing errors are on, but the letter body wasn't found, so none are added",
                                "template"))

    pn = settings.layout.page_numbers
    letters = []
    for n, record in enumerate(dataset.records, start=1):
        letter = merge_letter(n, template, record, dataset, profile, settings.merge)
        if settings.errors.enabled and has_body:
            seed = seed_for(letter_key(template_path, letter), settings.errors)
            letter.paragraphs, letter.typing_errors = add_typing_errors(
                letter.paragraphs, settings.errors, seed)
            if letter.typing_errors:
                listed = ", ".join(f"{e.typed} ({e.style})" for e in letter.typing_errors)
                letter.issues.append(I.info(f"typing errors: {listed}", f"letter {n} (row {record.row})", n))
        if pn.mode != "off":
            letter.page_number_text = merge_text(pn.format, record, dataset, settings.merge)
        letter.pages, layout_issues = layout_letter(
            letter.paragraphs, profile, settings.layout, letter.page_number_text,
            f"letter {n} (row {record.row})", n, frame)
        letter.issues += layout_issues
        letters.append(letter)
    return Merge(template, dataset, profile, settings, letters, issues, frame)
