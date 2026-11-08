"""Validation issues reported to the user."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Level(IntEnum):
    INFO = 0
    WARNING = 1
    ERROR = 2

    @property
    def label(self) -> str:
        return self.name.lower()


@dataclass(frozen=True)
class Issue:
    level: Level
    message: str
    where: str = ""  # "template", "data", "letter 3", "paragraph 7", ...
    letter: int | None = None  # 1-based letter number, if the issue belongs to one letter

    def __str__(self) -> str:
        where = f"{self.where}: " if self.where else ""
        return f"{self.level.label}: {where}{self.message}"


def info(message: str, where: str = "", letter: int | None = None) -> Issue:
    return Issue(Level.INFO, message, where, letter)


def warning(message: str, where: str = "", letter: int | None = None) -> Issue:
    return Issue(Level.WARNING, message, where, letter)


def error(message: str, where: str = "", letter: int | None = None) -> Issue:
    return Issue(Level.ERROR, message, where, letter)


def has_errors(issues) -> bool:
    return any(i.level is Level.ERROR for i in issues)
