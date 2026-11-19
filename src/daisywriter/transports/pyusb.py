"""USB printer-class parallel adapters through libusb (macOS and Linux).

Ported from ../olympia-compact-electronic-2/cmpprint.py (tested with a
Prolific PL2305, 067b:2305). On macOS libusb comes from the libusb-package
wheel, so it's inside the app; on Linux it's the system's. On Windows the inbox usbprint.sys driver owns these
adapters, so Windows uses transports/usbprint.py instead.
"""
from __future__ import annotations

from .base import UNPLUGGED, DeviceNotFound, PortStatus, TransportError, WriteStalled, WriteTimeout

ENDPOINT_OUT = 0x01


def _backend():
    """The libusb that comes with the libusb-package wheel (macOS), so the app
    doesn't need Homebrew; otherwise None, and pyusb looks for a system libusb."""
    try:
        import libusb_package
    except ImportError:
        return None
    return libusb_package.get_libusb1_backend()


def _failure(what: str, e) -> TransportError:
    if e.errno == 19:  # ENODEV: the adapter was unplugged
        return TransportError(f"{what} failed: {UNPLUGGED}")
    return TransportError(f"{what} failed: USB error: {e}")


class PyUsbTransport:
    def __init__(self, vid: int, pid: int):
        try:
            import usb.core
            import usb.util
        except ImportError as e:
            raise TransportError("pyusb isn't installed") from e
        self._usb = usb
        try:
            dev = usb.core.find(idVendor=vid, idProduct=pid, backend=_backend())
        except usb.core.NoBackendError as e:
            raise TransportError("libusb isn't installed (on macOS: brew install libusb)") from e
        if dev is None:
            raise DeviceNotFound(f"USB parallel adapter {vid:04x}:{pid:04x} not found; is it plugged in?")
        self.name = f"USB {vid:04x}:{pid:04x}"
        try:
            if dev.is_kernel_driver_active(0):
                dev.detach_kernel_driver(0)
        except (NotImplementedError, usb.core.USBError):
            pass
        try:
            cfg = dev.get_active_configuration()
        except usb.core.USBError:
            cfg = None
        if cfg is None:
            dev.set_configuration()  # only when unconfigured, to avoid resetting the adapter
        try:
            usb.util.claim_interface(dev, 0)
        except usb.core.USBError as e:
            raise TransportError(f"can't claim the adapter (is another program using it?): {e}") from e
        try:
            # SET_INTERFACE resets the adapter's endpoint state. After a stall it keeps
            # stalling every write even though GET_STATUS says the endpoint isn't halted;
            # clear_halt alone doesn't fix that.
            dev.set_interface_altsetting(interface=0, alternate_setting=0)
        except usb.core.USBError:
            pass
        try:
            dev.clear_halt(ENDPOINT_OUT)  # recover from an earlier timed-out write
        except usb.core.USBError:
            pass
        self._dev = dev

    def status(self) -> PortStatus:
        try:
            # USB printer class GET_PORT_STATUS
            return PortStatus.from_byte(self._dev.ctrl_transfer(0xA1, 1, 0, 0, 1)[0])
        except self._usb.core.USBError as e:
            raise _failure("reading the port status", e) from e

    def write(self, data: bytes, timeout_s: float) -> None:
        usb = self._usb
        try:
            n = self._dev.write(ENDPOINT_OUT, data, timeout=int(timeout_s * 1000))
        except usb.core.USBTimeoutError as e:
            raise WriteTimeout("the typewriter stopped taking data (off-line, BUSY stuck, "
                               "or it lost power)") from e
        except usb.core.USBError as e:
            if e.errno == 32:
                raise WriteStalled("the adapter stalled the write (USB pipe error); it does this "
                                   "while PE is high. Check the cable, then try again: opening "
                                   "the adapter resets it") from e
            raise _failure("writing", e) from e
        if n != len(data):
            raise TransportError(f"short write: {n} of {len(data)} bytes")

    def close(self) -> None:
        try:
            self._usb.util.release_interface(self._dev, 0)
        except self._usb.core.USBError:
            pass
