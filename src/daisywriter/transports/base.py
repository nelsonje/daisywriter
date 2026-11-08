"""The connection to a typewriter: the only part of daisywriter that needs hardware."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PortStatus:
    """Parallel-port status lines as reported by a USB printer-class adapter.

    raw is the GET_PORT_STATUS byte: bit 5 paper empty, bit 4 select, bit 3 not-error.
    """
    select: bool  # the typewriter is on-line
    paper_empty: bool
    error: bool
    raw: int

    @classmethod
    def from_byte(cls, s: int) -> PortStatus:
        return cls(select=bool(s & 0x10), paper_empty=bool(s & 0x20), error=not (s & 0x08), raw=s)

    @property
    def ready(self) -> bool:
        return self.select and not self.paper_empty and not self.error

    def explain(self) -> str:
        if self.paper_empty:
            # From cmpprint.py: the typewriter never drives PE, so PE high means the
            # cable is loose (the adapter reads 0x38 with nothing attached).
            return ("PE (paper empty) is high: the typewriter never drives this line, so check "
                    "that the parallel cable is plugged in at both ends")
        if not self.select:
            return "the typewriter is off-line: press ON LINE (its LED should light)"
        if self.error:
            return "the typewriter reports an error"
        return "ready"


class TransportError(Exception):
    """A problem talking to the typewriter, with a message for the user."""


class DeviceNotFound(TransportError):
    pass


class WriteTimeout(TransportError):
    pass


class WriteStalled(TransportError):
    pass


class Transport(Protocol):
    name: str

    def status(self) -> PortStatus | None:
        """Current port status, or None when the connection can't report it."""

    def write(self, data: bytes, timeout_s: float) -> None:
        """Send data; raises WriteTimeout if the typewriter stops taking it."""

    def close(self) -> None: ...
