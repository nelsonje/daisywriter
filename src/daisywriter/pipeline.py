"""Run the whole merge: template + data + profile -> validated, laid-out letters."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import issues as I
from .layout import LayoutSettings, layout_letter
from .merge import Letter, MergeSettings, merge_letter, merge_text
from .model import Template
from .profile import STOCKS, Profile, load_profile
from .records import DataSet, load_records, normalize
from .region import apply_regions
from .template import load_template


@dataclass
class Settings:
    profile: str | None = None  # built-in id or path to a .toml
    sheet: str | None = None
    merge: MergeSettings = field(default_factory=MergeSettings)
    layout: LayoutSettings = field(default_factory=LayoutSettings)
    closings: list[str] = field(default_factory=list)  # extra complimentary closes (regexes)


@dataclass
class Merge:
    template: Template
    dataset: DataSet
    profile: Profile
    settings: Settings
    letters: list[Letter]
    issues: list[I.Issue]  # template, data and cross-checks; letters carry their own

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


def check_profile(profile: Profile, settings: Settings) -> list[I.Issue]:
    stock = STOCKS[settings.layout.stock]
    issues = []
    paper_cols = int(stock.width_in * profile.pitch_cpi)
    if profile.margin_right > paper_cols:
        issues.append(I.warning(
            f"the right margin (column {profile.margin_right}) is past the edge of "
            f"{stock.name} paper ({paper_cols} columns at {profile.pitch_cpi} cpi)", "profile"))
    return issues


def run(template_path: str | Path, data_path: str | Path, settings: Settings | None = None) -> Merge:
    settings = settings or Settings()
    profile = load_profile(settings.profile)
    template = apply_regions(load_template(template_path), settings.closings)
    dataset = load_records(data_path, settings.sheet)
    issues = list(template.issues) + list(dataset.issues)
    issues += check_fields(template, dataset)
    issues += check_profile(profile, settings)

    pn = settings.layout.page_numbers
    letters = []
    for n, record in enumerate(dataset.records, start=1):
        letter = merge_letter(n, template, record, dataset, profile, settings.merge)
        if pn.mode != "off":
            letter.page_number_text = merge_text(pn.format, record, dataset, settings.merge)
        letter.pages, layout_issues = layout_letter(
            letter.paragraphs, profile, settings.layout, letter.page_number_text,
            f"letter {n} (row {record.row})", n)
        letter.issues += layout_issues
        letters.append(letter)
    return Merge(template, dataset, profile, settings, letters, issues)
