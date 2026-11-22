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


UNPLUGGED = "the adapter stopped responding: is the USB cable unplugged?"


@dataclass(frozen=True)
class Adapter:
    """A USB-to-parallel cable that works as a USB printer-class device."""
    vid: int
    pid: int
    name: str

    def __str__(self) -> str:
        return f"{self.name} ({self.vid:04x}:{self.pid:04x})"


# The cables daisywriter looks for, in this order. Any of them works with any
# typewriter; a profile's usb = { vid, pid } picks one instead.
ADAPTERS = (
    Adapter(0x067B, 0x2305, "Prolific PL2305 adapter"),
    Adapter(0x1A86, 0x7584, "Sabrent adapter (WCH CH340S)"),
)


def adapters_for(usb: dict | None) -> tuple[Adapter, ...]:
    """The adapters to look for: the profile's, if it names one, else every known one."""
    if not usb:
        return ADAPTERS
    vid, pid = int(usb["vid"]), int(usb["pid"])
    known = next((a for a in ADAPTERS if (a.vid, a.pid) == (vid, pid)), None)
    return (known or Adapter(vid, pid, "USB parallel adapter"),)


def not_found(adapters: tuple[Adapter, ...]) -> str:
    listed = " or ".join(f"{a.vid:04x}:{a.pid:04x}" for a in adapters)
    return f"no USB parallel adapter found ({listed}); is it plugged in?"


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
