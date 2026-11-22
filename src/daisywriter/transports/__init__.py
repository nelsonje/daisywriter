"""Connections to typewriters. open_transport() picks the right one for the profile
and opens the first known USB parallel adapter that's plugged in."""
from __future__ import annotations

import sys

from ..profile import Profile
from .base import (
    ADAPTERS,
    Adapter,
    DeviceNotFound,
    PortStatus,
    Transport,
    TransportError,
    WriteStalled,
    WriteTimeout,
    adapters_for,
)

__all__ = ["ADAPTERS", "Adapter", "DeviceNotFound", "PortStatus", "Transport", "TransportError",
           "WriteStalled", "WriteTimeout", "open_transport"]


def open_transport(profile: Profile, dry_run: str | None = None) -> Transport:
    if dry_run:
        from .file import FileTransport
        return FileTransport(dry_run)
    kind = profile.raw.get("transport", "usb_printer")
    if kind != "usb_printer":
        raise TransportError(f"the {kind!r} transport isn't implemented yet")
    adapters = adapters_for(profile.raw.get("usb"))
    if sys.platform == "win32":
        from .usbprint import UsbPrintTransport
        return UsbPrintTransport(adapters)
    from .pyusb import PyUsbTransport
    return PyUsbTransport(adapters)
