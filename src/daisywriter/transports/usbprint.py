"""USB printer-class parallel adapters on Windows, through the inbox usbprint.sys driver.

Windows binds usbprint.sys ("USB Printing Support") to these adapters, so no
driver needs installing and libusb can't claim them. daisywriter talks to the
driver directly, not through a print queue:
- SetupAPI lists the device interfaces of GUID_DEVINTERFACE_USBPRINT. Each
  device path names the USB vendor and product ("\\\\?\\usb#vid_067b&pid_2305#...").
- CreateFileW opens the one that matches the profile's vid/pid, overlapped.
- WriteFile sends a line; a write the typewriter doesn't take within the
  timeout is cancelled with CancelIoEx, so a stuck typewriter can't hang the job.
- IOCTL_USBPRINT_GET_LPT_STATUS reads the same port status byte as the USB
  printer class GET_PORT_STATUS that the pyusb transport reads on macOS.

Not yet tried with the typewriter: what the driver reports when the adapter
stalls (on macOS it stalls while PE is high) is unknown, so those errors are
reported with Windows' own message.
"""
from __future__ import annotations

import ctypes
import re
import sys
import uuid

from .base import UNPLUGGED, DeviceNotFound, PortStatus, TransportError, WriteTimeout

GUID_DEVINTERFACE_USBPRINT = uuid.UUID("28d78fad-5a12-11d1-ae5b-0000f803a8c2")
IOCTL_USBPRINT_GET_LPT_STATUS = 0x220030
IOCTL_USBPRINT_SOFT_RESET = 0x220040

DIGCF_PRESENT, DIGCF_DEVICEINTERFACE = 0x02, 0x10
GENERIC_READ, GENERIC_WRITE = 0x80000000, 0x40000000
FILE_SHARE_READ, FILE_SHARE_WRITE = 0x1, 0x2
OPEN_EXISTING, FILE_FLAG_OVERLAPPED = 3, 0x40000000
ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND, ERROR_ACCESS_DENIED = 2, 3, 5
ERROR_INSUFFICIENT_BUFFER, ERROR_NO_MORE_ITEMS, ERROR_IO_PENDING = 122, 259, 997
ERROR_OPERATION_ABORTED = 995
WAIT_OBJECT_0, WAIT_TIMEOUT = 0, 0x102

_VID_PID = re.compile(r"vid_([0-9a-f]{4})&pid_([0-9a-f]{4})", re.IGNORECASE)


def vid_pid(device_path: str) -> tuple[int, int] | None:
    """The USB vendor and product ids in a device interface path."""
    m = _VID_PID.search(device_path)
    return (int(m.group(1), 16), int(m.group(2), 16)) if m else None


def pick_device(paths: list[str], vid: int, pid: int) -> str | None:
    return next((p for p in paths if vid_pid(p) == (vid, pid)), None)


if sys.platform == "win32":
    from ctypes import wintypes

    _setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8)]

        @classmethod
        def from_uuid(cls, u: uuid.UUID) -> GUID:
            g = cls(u.fields[0], u.fields[1], u.fields[2])
            g.Data4[:] = list(u.bytes[8:])
            return g

    class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("InterfaceClassGuid", GUID),
                    ("Flags", wintypes.DWORD), ("Reserved", ctypes.c_size_t)]

    class OVERLAPPED(ctypes.Structure):
        _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t),
                    ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD),
                    ("hEvent", wintypes.HANDLE)]

    def _fn(dll, name, restype, *argtypes):
        f = getattr(dll, name)
        f.restype, f.argtypes = restype, list(argtypes)
        return f

    _GetClassDevs = _fn(_setupapi, "SetupDiGetClassDevsW", wintypes.HANDLE,
                        ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD)
    _EnumInterfaces = _fn(_setupapi, "SetupDiEnumDeviceInterfaces", wintypes.BOOL, wintypes.HANDLE,
                          ctypes.c_void_p, ctypes.POINTER(GUID), wintypes.DWORD,
                          ctypes.POINTER(SP_DEVICE_INTERFACE_DATA))
    _InterfaceDetail = _fn(_setupapi, "SetupDiGetDeviceInterfaceDetailW", wintypes.BOOL,
                           wintypes.HANDLE, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA), ctypes.c_void_p,
                           wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p)
    _DestroyList = _fn(_setupapi, "SetupDiDestroyDeviceInfoList", wintypes.BOOL, wintypes.HANDLE)
    _CreateFile = _fn(_kernel32, "CreateFileW", wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD,
                      wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    _CreateEvent = _fn(_kernel32, "CreateEventW", wintypes.HANDLE, ctypes.c_void_p, wintypes.BOOL,
                       wintypes.BOOL, wintypes.LPCWSTR)
    _WriteFile = _fn(_kernel32, "WriteFile", wintypes.BOOL, wintypes.HANDLE, ctypes.c_void_p,
                     wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(OVERLAPPED))
    _DeviceIoControl = _fn(_kernel32, "DeviceIoControl", wintypes.BOOL, wintypes.HANDLE, wintypes.DWORD,
                           ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                           ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(OVERLAPPED))
    _GetOverlappedResult = _fn(_kernel32, "GetOverlappedResult", wintypes.BOOL, wintypes.HANDLE,
                               ctypes.POINTER(OVERLAPPED), ctypes.POINTER(wintypes.DWORD), wintypes.BOOL)
    _CancelIoEx = _fn(_kernel32, "CancelIoEx", wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(OVERLAPPED))
    _WaitForSingleObject = _fn(_kernel32, "WaitForSingleObject", wintypes.DWORD, wintypes.HANDLE,
                               wintypes.DWORD)
    _ResetEvent = _fn(_kernel32, "ResetEvent", wintypes.BOOL, wintypes.HANDLE)
    _CloseHandle = _fn(_kernel32, "CloseHandle", wintypes.BOOL, wintypes.HANDLE)


def _message(code: int) -> str:
    return f"{ctypes.FormatError(code).strip()} (Windows error {code})"


# What a write or a status read on an open handle gets once the adapter is gone.
# Pulling the USB cable while a write waited gave ERROR_GEN_FAILURE (2026-11-18);
# a write sent after the cable was out gave ERROR_ACCESS_DENIED (2026-11-22). On an
# open handle that can only mean the device went away; opening a device another
# program holds also gives it, but __init__ handles that case itself.
GONE = {5: "ERROR_ACCESS_DENIED", 31: "ERROR_GEN_FAILURE", 433: "ERROR_NO_SUCH_DEVICE",
        1167: "ERROR_DEVICE_NOT_CONNECTED", 1617: "ERROR_DEVICE_REMOVED"}


def _failure(what: str, code: int) -> TransportError:
    if code in GONE:
        return TransportError(f"{what} failed: {UNPLUGGED} (Windows error {code})")
    return TransportError(f"{what} failed: {_message(code)}")


def usbprint_paths() -> list[str]:
    """Device paths of every USB printer-class device that's plugged in."""
    guid = GUID.from_uuid(GUID_DEVINTERFACE_USBPRINT)
    devs = _GetClassDevs(ctypes.byref(guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if devs == INVALID_HANDLE_VALUE:
        raise TransportError(f"can't list USB printer devices: {_message(ctypes.get_last_error())}")
    paths = []
    try:
        index = 0
        while True:
            data = SP_DEVICE_INTERFACE_DATA(cbSize=ctypes.sizeof(SP_DEVICE_INTERFACE_DATA))
            if not _EnumInterfaces(devs, None, ctypes.byref(guid), index, ctypes.byref(data)):
                if ctypes.get_last_error() == ERROR_NO_MORE_ITEMS:
                    break
                raise TransportError(f"can't list USB printer devices: {_message(ctypes.get_last_error())}")
            index += 1
            need = wintypes.DWORD()
            _InterfaceDetail(devs, ctypes.byref(data), None, 0, ctypes.byref(need), None)
            buf = ctypes.create_string_buffer(need.value)
            # SP_DEVICE_INTERFACE_DETAIL_DATA_W: cbSize is the fixed part's size, 8 on 64-bit
            ctypes.c_uint32.from_buffer(buf).value = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            if _InterfaceDetail(devs, ctypes.byref(data), buf, need, None, None):
                paths.append(ctypes.wstring_at(ctypes.addressof(buf) + 4))
    finally:
        _DestroyList(devs)
    return paths


class UsbPrintTransport:
    def __init__(self, vid: int = 0x067B, pid: int = 0x2305, path: str | None = None):
        if sys.platform != "win32":
            raise TransportError("the usbprint transport only works on Windows")
        if path is None:
            path = pick_device(usbprint_paths(), vid, pid)
            if path is None:
                raise DeviceNotFound(f"USB parallel adapter {vid:04x}:{pid:04x} not found; is it plugged "
                                     "in? (Device Manager should list it as USB Printing Support)")
        self.name = f"USB {vid:04x}:{pid:04x}"
        self.path = path
        h = _CreateFile(path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, None,
                        OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)
        if h == INVALID_HANDLE_VALUE:
            code = ctypes.get_last_error()
            if code in (ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND):
                raise DeviceNotFound(f"the adapter went away while opening it: {_message(code)}")
            if code == ERROR_ACCESS_DENIED:
                raise TransportError("can't open the adapter: another program is using it (a Windows "
                                     "printer set up on this port may be printing)")
            raise TransportError(f"can't open the adapter: {_message(code)}")
        self._h = h
        self._event = _CreateEvent(None, True, False, None)

    def _io(self, start, timeout_s: float, what: str, timed_out: str = "") -> int:
        """Run one overlapped call; returns the bytes transferred."""
        ov = OVERLAPPED(hEvent=self._event)
        _ResetEvent(self._event)
        done = wintypes.DWORD()
        if not start(ctypes.byref(ov)):
            code = ctypes.get_last_error()
            if code != ERROR_IO_PENDING:
                raise _failure(what, code)
            if _WaitForSingleObject(self._event, max(1, int(timeout_s * 1000))) == WAIT_TIMEOUT:
                _CancelIoEx(self._h, ctypes.byref(ov))
                _GetOverlappedResult(self._h, ctypes.byref(ov), ctypes.byref(done), True)  # let it finish
                raise WriteTimeout(timed_out or f"{what} timed out")
        if not _GetOverlappedResult(self._h, ctypes.byref(ov), ctypes.byref(done), True):
            raise _failure(what, ctypes.get_last_error())
        return done.value

    def status(self) -> PortStatus:
        out = ctypes.c_ubyte()
        returned = wintypes.DWORD()
        self._io(lambda ov: _DeviceIoControl(self._h, IOCTL_USBPRINT_GET_LPT_STATUS, None, 0,
                                             ctypes.byref(out), 1, ctypes.byref(returned), ov),
                 5.0, "reading the port status")
        return PortStatus.from_byte(out.value)

    def write(self, data: bytes, timeout_s: float) -> None:
        sent = 0
        while sent < len(data):
            chunk = (ctypes.c_char * (len(data) - sent)).from_buffer_copy(data[sent:])
            n = self._io(lambda ov, c=chunk: _WriteFile(self._h, c, len(c), None, ov), timeout_s, "writing",
                         "the typewriter stopped taking data (off-line, BUSY stuck, or it lost power)")
            if n == 0:
                raise TransportError(f"short write: {sent} of {len(data)} bytes")
            sent += n

    def soft_reset(self) -> None:
        """USB printer class SOFT_RESET: flushes the adapter's buffers and clears a
        stalled pipe. Not used automatically: what it does to the typewriter is untested."""
        returned = wintypes.DWORD()
        self._io(lambda ov: _DeviceIoControl(self._h, IOCTL_USBPRINT_SOFT_RESET, None, 0, None, 0,
                                             ctypes.byref(returned), ov), 5.0, "resetting the adapter")

    def close(self) -> None:
        if getattr(self, "_h", None):
            _CloseHandle(self._h)
            _CloseHandle(self._event)
            self._h = None
