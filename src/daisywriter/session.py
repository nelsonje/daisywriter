"""Which letters have been printed, saved next to the data file.

A merge of report.docx with clients.xlsx keeps its state in
clients.daisywriter.json, so after a paper jam, a crash or a day off the user
can see what's done and print the rest. Letters are matched by template name,
spreadsheet row and the row's values: editing a row makes its letter "not
printed" again. A letter whose content changed for another reason (the
template text, today's date) keeps its status but is flagged as changed.

It also keeps the typing-error salts: re-rolling gives one letter, or all of
them, new errors, and the same errors come back the next time.
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
    salt: int = 0  # typing errors: re-rolls of every letter
    salts: dict[str, int] = field(default_factory=dict)  # re-rolls of single letters
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
            s.salt = int(raw.get("salt", 0))
            s.salts = {k: int(v) for k, v in raw.get("salts", {}).items()}
        except (OSError, ValueError, TypeError) as e:
            s.problem = f"couldn't read {path.name} ({e}); print statuses start fresh"
        return s

    def save(self) -> None:
        data = {"version": VERSION, "letters": {k: asdict(v) for k, v in sorted(self.letters.items())},
                "salt": self.salt, "salts": dict(sorted(self.salts.items()))}
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def state(self, template: str | Path, letter: Letter) -> LetterState:
        return self.letters.get(letter_key(template, letter), LetterState())

    def reroll(self, template: str | Path | None = None, letter: Letter | None = None) -> None:
        """New typing errors for one letter, or for all of them."""
        if letter is None:
            self.salt += 1
        else:
            key = letter_key(template, letter)
            self.salts[key] = self.salts.get(key, 0) + 1
        self.save()

    def mark(self, template: str | Path, letter: Letter, status: str, message: str = "") -> LetterState:
        st = LetterState(status, dt.datetime.now().isoformat(timespec="seconds"),
                         letter_content(letter) if status == PRINTED else "", message)
        self.letters[letter_key(template, letter)] = st
        self.save()
        return st
