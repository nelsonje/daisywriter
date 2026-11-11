"""Which letters have been printed, saved next to the data file.

A merge of report.docx with clients.xlsx keeps its state in
clients.daisywriter.json, so after a paper jam, a crash or a day off the user
can see what's done and print the rest. Letters are matched by template name,
spreadsheet row and the row's values: editing a row makes its letter "not
printed" again. A letter whose content changed for another reason (the
template text, today's date) keeps its status but is flagged as changed.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .merge import Letter

NOT_PRINTED, PRINTING, PRINTED, FAILED = "not printed", "printing", "printed", "failed"
VERSION = 1


def session_path(data_path: str | Path) -> Path:
    p = Path(data_path)
    return p.with_name(p.stem + ".daisywriter.json")


def _digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def letter_key(template: str | Path, letter: Letter) -> str:
    return f"{Path(template).name}|row {letter.record.row}|{_digest(letter.record.values)}"


def letter_content(letter: Letter) -> str:
    """A fingerprint of what gets typed, formatting included."""
    pages = [[[(c.ch, c.bold, c.underline, c.strike) for c in line.cells] for line in p.lines]
             for p in letter.pages]
    return _digest(pages)


@dataclass
class LetterState:
    status: str = NOT_PRINTED
    when: str = ""  # ISO time of the last change
    content: str = ""  # letter_content when it was printed
    message: str = ""  # why it failed

    def changed_since(self, letter: Letter) -> bool:
        return self.status == PRINTED and bool(self.content) and self.content != letter_content(letter)


@dataclass
class Session:
    path: Path
    letters: dict[str, LetterState] = field(default_factory=dict)
    problem: str = ""  # set when an existing file couldn't be read

    @classmethod
    def load(cls, data_path: str | Path) -> Session:
        path = session_path(data_path)
        s = cls(path)
        if not path.exists():
            return s
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            s.letters = {k: LetterState(**v) for k, v in raw.get("letters", {}).items()}
        except (OSError, ValueError, TypeError) as e:
            s.problem = f"couldn't read {path.name} ({e}); print statuses start fresh"
        return s

    def save(self) -> None:
        data = {"version": VERSION, "letters": {k: asdict(v) for k, v in sorted(self.letters.items())}}
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def state(self, template: str | Path, letter: Letter) -> LetterState:
        return self.letters.get(letter_key(template, letter), LetterState())

    def mark(self, template: str | Path, letter: Letter, status: str, message: str = "") -> LetterState:
        st = LetterState(status, dt.datetime.now().isoformat(timespec="seconds"),
                         letter_content(letter) if status == PRINTED else "", message)
        self.letters[letter_key(template, letter)] = st
        self.save()
        return st
