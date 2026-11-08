"""Connections to typewriters. open_transport() picks the right one for the profile."""
from __future__ import annotations

import sys

from ..profile import Profile
from .base import DeviceNotFound, PortStatus, Transport, TransportError, WriteStalled, WriteTimeout

__all__ = ["DeviceNotFound", "PortStatus", "Transport", "TransportError", "WriteStalled",
           "WriteTimeout", "open_transport"]


def open_transport(profile: Profile, dry_run: str | None = None) -> Transport:
    if dry_run:
        from .file import FileTransport
        return FileTransport(dry_run)
    kind = profile.raw.get("transport", "usb_printer")
    if kind != "usb_printer":
        raise TransportError(f"the {kind!r} transport isn't implemented yet")
    usb = profile.raw.get("usb", {})
    vid, pid = int(usb.get("vid", 0x067B)), int(usb.get("pid", 0x2305))
    if sys.platform == "win32":
        raise TransportError("printing from Windows comes in phase 4 (usbprint.sys transport)")
    from .pyusb import PyUsbTransport
    return PyUsbTransport(vid, pid)
