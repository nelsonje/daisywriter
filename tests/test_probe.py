"""The Stop probe, against a scripted typewriter on a fake clock."""
from daisywriter.probe import probe
from daisywriter.profile import load_profile
from daisywriter.transports import PortStatus

PROFILE = load_profile("swintec-1146cmp")


class Scripted:
    """Takes `room` bytes at once, then one byte per `per_byte` seconds; the status
    reads `busy` for the first `typing` seconds after a write, else 0x18."""
    name = "scripted"

    def __init__(self, room=80, per_byte=0.1, busy=None, typing=6.0):
        self.now, self.taken, self.room, self.per_byte = 0.0, 0, room, per_byte
        self.busy, self.typing, self.last_write = busy, typing, None
        self.data = b""

    def clock(self):
        return self.now

    def sleep(self, s):
        self.now += s

    def status(self):
        busy = self.busy is not None and self.last_write is not None and self.now - self.last_write < self.typing
        return PortStatus.from_byte(self.busy if busy else 0x18)

    def write(self, data, timeout_s):
        if len(data) == 1 and self.taken >= self.room:
            self.now += self.per_byte
        self.taken += len(data) if len(data) == 1 else 0
        self.data += data
        self.last_write = self.now


def run(t, **kw):
    lines = []
    result = probe(t, PROFILE, lines.append, clock=t.clock, sleep=t.sleep, **kw)
    return result, "\n".join(lines)


def test_no_busy_signal_and_the_buffer_size():
    t = Scripted(room=80)
    result, text = run(t, lines=4)
    assert t.data.startswith(b"1: The quick brown fox") and t.data.count(b"\n") == 5
    assert result.line_bytes == len(b"2: The quick brown fox jumps over the lazy dog. 0123456789\n")
    assert result.burst == 80 and result.waits[0][0] == 80
    assert "status didn't change" in text and "80 bytes went in before the first wait" in text
    assert "first wait was at line 3, column 22; 156 write(s)" in text  # line 3 on the paper
    assert "line 2: bytes taken from   0.00 s to   0.00 s; 0 write(s) waited" in text


def test_a_status_bit_that_follows_the_typing():
    result, text = run(Scripted(busy=0x98), lines=1)
    assert [raw for _, raw in result.status_log] == [0x98, 0x18]
    assert "status changed while the line was typed" in text and "0x98 at 0.00 s" in text
    assert result.burst == result.line_bytes and not result.waits  # one line fits
