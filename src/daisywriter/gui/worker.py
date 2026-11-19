"""Runs a print job on a background thread so the window stays responsive.

The job's paper prompts go to the window as a signal, and the worker waits
until the window answers. Letters are printed one at a time, so each one's
status can be saved as soon as it's known.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal, Slot

from ..job import PrintCancelled, PrintOptions, print_letters
from ..merge import Letter
from ..profile import Profile
from ..session import FAILED, NOT_PRINTED, PRINTED, PRINTING
from ..transports import Transport, TransportError

STOPPED_PART_WAY = ("was stopped part way through. The typewriter may still type a line or two "
                    "that it already had. When it stops, take the sheet out and print the letter "
                    "again on a fresh sheet.")


class PrintWorker(QObject):
    asked = Signal(str)  # a question for the user; reply with answer()
    progress = Signal(int, int, int, int)  # letter, page, lines sent, lines on the page
    letter_state = Signal(int, str, str)  # letter number, status, message
    finished = Signal(str)  # a summary for the user

    def __init__(self, transport: Transport, letters: list[Letter], profile: Profile,
                 opts: PrintOptions, auto_yes: bool = False):
        super().__init__()
        self.transport, self.letters, self.profile, self.opts = transport, letters, profile, opts
        self.auto_yes = auto_yes
        self._answer = False
        self._answered = threading.Event()
        self._stop = threading.Event()
        self._sent = 0  # lines sent for the current letter

    def answer(self, yes: bool):
        self._answer = yes
        self._answered.set()

    def stop(self):
        """Stop before the next line. The typewriter still types what it already has:
        the line it's on and up to two more queued in it and the adapter."""
        self._stop.set()
        self.answer(False)  # in case a prompt is waiting

    def _ask(self, message: str) -> bool:
        if self.auto_yes:
            return True
        if self._stop.is_set():
            return False
        self._answered.clear()
        self.asked.emit(message)
        self._answered.wait()
        return self._answer

    def _progress(self, letter: int, page: int, sent: int, total: int):
        self._sent += 1
        self.progress.emit(letter, page, sent, total)

    @Slot()
    def run(self):
        done, summary = 0, ""
        try:
            for letter in self.letters:
                if self._stop.is_set():
                    summary = "Stopped."
                    break
                self._sent = 0
                self.letter_state.emit(letter.number, PRINTING, "")
                try:
                    print_letters(self.transport, [letter], self.profile, self.opts, self._ask,
                                  lambda s: None, self._stop.is_set, self._progress)
                except PrintCancelled:
                    if self._sent:
                        self.letter_state.emit(letter.number, FAILED, "stopped part way through")
                        summary = f"Letter {letter.number} {STOPPED_PART_WAY}"
                    else:
                        self.letter_state.emit(letter.number, NOT_PRINTED, "")
                        summary = "Stopped."
                    break
                except TransportError as e:
                    self.letter_state.emit(letter.number, FAILED, str(e))
                    summary = f"Letter {letter.number} failed: {e}"
                    break
                except Exception as e:  # noqa: BLE001 - report it rather than lose the thread
                    self.letter_state.emit(letter.number, FAILED, f"{type(e).__name__}: {e}")
                    summary = f"Letter {letter.number} failed: {type(e).__name__}: {e}"
                    break
                self.letter_state.emit(letter.number, PRINTED, "")
                done += 1
        finally:
            self.transport.close()
        n = len(self.letters)
        self.finished.emit(f"{done} of {n} letter{'s' if n != 1 else ''} printed. {summary}".strip())
