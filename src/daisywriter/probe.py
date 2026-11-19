"""Measure how far ahead of the typewriter the adapter takes data.

Stop can only hold back lines the typewriter hasn't been sent. A write returns
once the adapter has taken the bytes, so on Windows (2026-11-18) Stop came about
two lines late: the adapter and the typewriter held them already. This probe
finds out what a better Stop could wait for, in two runs:

1. One line, then the port status polled while it's typed. If a status bit
   follows the typing (a BUSY the adapter passes on), the job can wait for it.
2. Lines sent one byte at a time with no pauses. The bytes that go in before the
   first write has to wait are what the adapter and typewriter buffer; where
   the later waits fall (line ends, or every so many bytes) shows how the
   typewriter takes data.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from .profile import Profile
from .render import newline
from .transports import Transport

TEXT = "{n}: The quick brown fox jumps over the lazy dog. 0123456789"


@dataclass
class ProbeResult:
    line_bytes: int = 0  # bytes per line in run 2, with the newline (lines are numbered from 2)
    status_log: list[tuple[float, int]] = field(default_factory=list)  # run 1: (s, raw) on change
    burst: int = 0  # run 2: bytes taken before the first wait
    waits: list[tuple[int, float, float]] = field(default_factory=list)  # (byte, at s, waited s)

    def summary(self) -> list[str]:
        out = []
        raws = {raw for _, raw in self.status_log}
        if len(raws) <= 1:
            out.append("Run 1: the status didn't change while the line was typed, so it can't tell "
                       "when the typewriter is busy.")
        else:
            out.append("Run 1: the status changed while the line was typed: "
                       + ", ".join(f"{raw:#04x} at {s:.2f} s" for s, raw in self.status_log) + ".")
        if self.line_bytes:
            out.append(f"Run 2: {self.burst} bytes went in before the first wait "
                       f"(about {self.burst / self.line_bytes:.1f} lines of {self.line_bytes} bytes).")
        if self.waits:
            i = self.waits[0][0]
            out.append(f"Run 2: the first wait was at line {i // self.line_bytes + 2}, column "
                       f"{i % self.line_bytes + 1}; {len(self.waits)} write(s) waited in all.")
        return out


def probe(t: Transport, profile: Profile, report: Callable[[str], None] = print, lines: int = 4,
          watch_s: float = 12.0, poll_s: float = 0.02, wait_s: float = 0.05,
          clock: Callable[[], float] = time.monotonic,
          sleep: Callable[[float], None] = time.sleep) -> ProbeResult:
    nl = newline(profile)
    width = profile.line_width
    result = ProbeResult()

    report("Run 1: one line, then the status while it's typed")
    t.write(TEXT.format(n=1)[:width].encode("ascii") + nl, 60.0)
    start, last = clock(), None
    while clock() - start < watch_s:
        st = t.status()
        if st is not None and st.raw != last:
            last = st.raw
            result.status_log.append((clock() - start, st.raw))
            report(f"  {clock() - start:6.2f} s  status {st.raw:#04x} ({st.explain()})")
        sleep(poll_s)

    report(f"Run 2: {lines} lines a byte at a time")
    # lines 2-9: the same length, so a byte's line and column follow from its index
    text = [TEXT.format(n=n)[:width].encode("ascii") + nl for n in range(2, min(lines, 8) + 2)]
    result.line_bytes = len(text[0])
    data = b"".join(text)
    start = clock()
    result.burst = len(data)
    first, waited_in_line, waits_in_line = 0.0, 0.0, 0
    for i in range(len(data)):
        t0 = clock()
        if i % result.line_bytes == 0:
            first, waited_in_line, waits_in_line = t0 - start, 0.0, 0
        t.write(data[i:i + 1], 60.0)
        waited = clock() - t0
        if waited > wait_s:
            if not result.waits:
                result.burst = i
            result.waits.append((i, t0 - start, waited))
            waited_in_line += waited
            waits_in_line += 1
        if (i + 1) % result.line_bytes == 0:
            report(f"  line {i // result.line_bytes + 2}: bytes taken from {first:6.2f} s to "
                   f"{clock() - start:6.2f} s; {waits_in_line} write(s) waited, {waited_in_line:.2f} s in all")
    for line in result.summary():
        report(line)
    return result
