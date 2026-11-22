"""USB printer-class parallel adapters through libusb (macOS and Linux).

Ported from ../olympia-compact-electronic-2/cmpprint.py (tested with a
Prolific PL2305, 067b:2305). The OUT endpoint comes from the adapter's
descriptors: 0x01 on the Prolific, 0x02 on the Sabrent. On macOS libusb comes from the libusb-package
wheel, so it's inside the app; on Linux it's the system's. On Windows the inbox usbprint.sys driver owns these
adapters, so Windows uses transports/usbprint.py instead.
"""
from __future__ import annotations

from .base import (
    ADAPTERS,
    UNPLUGGED,
    Adapter,
    DeviceNotFound,
    PortStatus,
    TransportError,
    WriteStalled,
    WriteTimeout,
    not_found,
)

ENDPOINT_OUT = 0x01  # when the descriptors don't say


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


def _endpoint_out(dev) -> int:
    """The bulk OUT endpoint of interface 0."""
    import usb.core
    try:
        endpoints = list(dev.get_active_configuration()[(0, 0)])
    except (usb.core.USBError, KeyError, IndexError):
        return ENDPOINT_OUT
    return next((ep.bEndpointAddress for ep in endpoints
                 if not ep.bEndpointAddress & 0x80 and ep.bmAttributes & 0x03 == 0x02), ENDPOINT_OUT)


class PyUsbTransport:
    def __init__(self, adapters: tuple[Adapter, ...] = ADAPTERS):
        try:
            import usb.core
            import usb.util
        except ImportError as e:
            raise TransportError("pyusb isn't installed") from e
        self._usb = usb
        dev = None
        try:
            for adapter in adapters:
                dev = usb.core.find(idVendor=adapter.vid, idProduct=adapter.pid, backend=_backend())
                if dev is not None:
                    break
        except usb.core.NoBackendError as e:
            raise TransportError("libusb isn't installed (on macOS: brew install libusb)") from e
        if dev is None:
            raise DeviceNotFound(not_found(adapters))
        self.name = str(adapter)
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
        self._out = _endpoint_out(dev)
        try:
            dev.clear_halt(self._out)  # recover from an earlier timed-out write
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
            n = self._dev.write(self._out, data, timeout=int(timeout_s * 1000))
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
