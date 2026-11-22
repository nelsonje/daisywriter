"""The Windows usbprint transport. Device-path matching runs everywhere; the
ctypes calls run on Windows (CI), against SetupAPI with no adapter plugged in
and against a named pipe standing in for the adapter."""
import sys
import uuid

import pytest

from daisywriter.transports import DeviceNotFound, TransportError, WriteTimeout, adapters_for
from daisywriter.transports.usbprint import pick_device, vid_pid

PATHS = [
    r"\\?\usb#vid_04b8&pid_0005#5&1a2b3c&0&2#{28d78fad-5a12-11d1-ae5b-0000f803a8c2}",
    r"\\?\USB#VID_067B&PID_2305#5&2b3c4d&0&3#{28d78fad-5a12-11d1-ae5b-0000f803a8c2}",
    r"\\?\USB#VID_1A86&PID_7584#5&3c4d5e&0&4#{28d78fad-5a12-11d1-ae5b-0000f803a8c2}",
]
windows = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def test_vid_pid_from_device_paths():
    assert vid_pid(PATHS[1]) == (0x067B, 0x2305)
    assert vid_pid(r"\\?\root#something") is None
    path, adapter = pick_device(PATHS)
    assert path == PATHS[1] and str(adapter) == "Prolific PL2305 adapter (067b:2305)"
    path, adapter = pick_device([PATHS[0], PATHS[2]])  # only the Sabrent: the printer is never picked
    assert path == PATHS[2] and str(adapter) == "Sabrent adapter (WCH CH340S) (1a86:7584)"
    assert pick_device(PATHS[:1]) is None
    assert pick_device(PATHS, adapters_for({"vid": 0x1A86, "pid": 0x7584}))[0] == PATHS[2]
    assert pick_device(PATHS, adapters_for({"vid": 0x1234, "pid": 0x5678})) is None


def test_unplugged_adapter_says_so():
    from daisywriter.transports.usbprint import _failure
    e = _failure("writing", 31)  # what pulling the USB cable gave on 2026-11-18
    assert str(e) == ("writing failed: the adapter stopped responding: is the USB cable unplugged? "
                      "(Windows error 31)")
    assert "USB cable unplugged" in str(_failure("reading the port status", 1167))
    assert "USB cable unplugged" in str(_failure("writing", 5))  # a write after the pull, 2026-11-22


def test_unplugged_adapter_says_so_with_libusb():
    from daisywriter.transports.pyusb import _failure

    class USBError(Exception):
        errno = 19
    assert "is the USB cable unplugged?" in str(_failure("writing", USBError("No such device")))
    USBError.errno = 5
    assert str(_failure("writing", USBError("Input/Output Error"))) == \
        "writing failed: USB error: Input/Output Error"


def test_only_on_windows():
    if sys.platform == "win32":
        pytest.skip("this checks the error on other systems")
    from daisywriter.transports.usbprint import UsbPrintTransport
    with pytest.raises(TransportError, match="only works on Windows"):
        UsbPrintTransport()


@windows
def test_setupapi_lists_devices():
    from daisywriter.transports.usbprint import UsbPrintTransport, usbprint_paths
    paths = usbprint_paths()  # CI has no USB printers; this checks the ctypes calls
    assert isinstance(paths, list)
    if pick_device(paths, adapters_for({"vid": 0x1234, "pid": 0x5678})) is None:
        with pytest.raises(DeviceNotFound, match="1234:5678"):
            UsbPrintTransport(adapters_for({"vid": 0x1234, "pid": 0x5678}))


@windows
def test_overlapped_write_and_timeout_through_a_named_pipe():
    import _winapi

    from daisywriter.transports.usbprint import UsbPrintTransport
    name = rf"\\.\pipe\daisywriter-test-{uuid.uuid4().hex}"
    server = _winapi.CreateNamedPipe(
        name, _winapi.PIPE_ACCESS_DUPLEX,
        0,  # PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT, all 0 (_winapi doesn't name them)
        1, 4096, 4096, 0, _winapi.NULL)
    try:
        t = UsbPrintTransport(path=name)
        t.write(b"Dear Ann,\n", 2.0)
        data, _ = _winapi.ReadFile(server, 100)
        assert data == b"Dear Ann,\n"
        with pytest.raises(WriteTimeout, match="stopped taking data"):
            t.write(b"x" * 1_000_000, 0.3)  # nobody reads: the write is cancelled
        with pytest.raises(TransportError):
            t.status()  # a pipe isn't a printer
        t.close()
        t.close()  # closing twice is harmless
    finally:
        _winapi.CloseHandle(server)
