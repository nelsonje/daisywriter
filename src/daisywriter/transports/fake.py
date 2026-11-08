"""A typewriter stand-in for tests and GUI development.

Records every write. Statuses and failures can be queued to simulate a
typewriter going off-line, a loose cable, or a write timeout.
"""
from __future__ import annotations

from .base import PortStatus, WriteTimeout


class FakeTransport:
    name = "fake typewriter"

    def __init__(self, status: int = 0x18):
        self.writes: list[bytes] = []
        self.statuses: list[int] = []  # returned first, one per status() call
        self.default_status = status
        self.fail_after: int | None = None  # raise WriteTimeout on this write number (0-based)
        self.closed = False

    @property
    def data(self) -> bytes:
        return b"".join(self.writes)

    def status(self) -> PortStatus:
        raw = self.statuses.pop(0) if self.statuses else self.default_status
        return PortStatus.from_byte(raw)

    def write(self, data: bytes, timeout_s: float) -> None:
        if self.fail_after is not None and len(self.writes) >= self.fail_after:
            raise WriteTimeout("simulated timeout")
        self.writes.append(bytes(data))

    def close(self) -> None:
        self.closed = True
