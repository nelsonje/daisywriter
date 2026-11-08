"""Dry run: write the bytes to a file instead of a typewriter."""
from __future__ import annotations

from pathlib import Path

from .base import PortStatus


class FileTransport:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.name = f"file {self.path}"
        self._f = open(self.path, "wb")  # noqa: SIM115 - closed in close()

    def status(self) -> PortStatus:
        return PortStatus.from_byte(0x18)  # always ready

    def write(self, data: bytes, timeout_s: float) -> None:
        self._f.write(data)

    def close(self) -> None:
        self._f.close()
