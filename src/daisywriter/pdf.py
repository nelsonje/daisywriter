"""Draw emulated sheets as a PDF, one page per sheet, at true size.

Every strike is drawn where the typewriter would put it, in Courier at 12 pt
(10 characters per inch), slightly transparent so overstrikes show darker.
Strikes the carrier reached from the right are shifted by the carrier play
measured on the Swintec (a guess at its size: "slightly thicker").
Printed at 100 % on an ordinary printer, the PDF shows where text lands on
the sheet, e.g. against pre-printed letterhead.
"""
from __future__ import annotations

from pathlib import Path

from .profile import STOCKS
from .transports.emulator import STEPS_PER_INCH, UNITS_PER_INCH, Sheet

PT = 72  # points per inch
CARRIER_PLAY_IN = 0.006  # shift of a strike reached from the right
INK = 0.85  # opacity of one strike


def _escape(text: str) -> bytes:
    raw = text.encode("cp1252", errors="replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def page_content(sheet: Sheet, height_pt: float, paper_left_in: float = 0.0,
                 play_in: float = CARRIER_PLAY_IN) -> bytes:
    out = [b"/GS1 gs BT /F1 12 Tf"]
    for s in sheet.strikes:
        x = (paper_left_in + s.x / STEPS_PER_INCH + (play_in if s.from_right else 0)) * PT
        y = height_pt - s.y / UNITS_PER_INCH * PT
        out.append(b"1 0 0 1 %.2f %.2f Tm (%s) Tj" % (x, y, _escape(s.ch)))
    out.append(b"ET")
    return b"\n".join(out)


def write_pdf(path: str | Path, sheets: list[Sheet], stock: str = "letter",
              paper_left_in: float = 0.0, play_in: float = CARRIER_PLAY_IN) -> None:
    """paper_left_in: where the sheet's left edge sits relative to the
    carrier's column 0 (the left stop); 0 puts margin column 10 1 inch in."""
    w, h = STOCKS[stock].width_in * PT, STOCKS[stock].length_in * PT
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",  # pages, filled in below
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>",
        b"<< /Type /ExtGState /ca %.2f >>" % INK,
    ]
    kids = []
    for sheet in sheets or [Sheet(1, 0)]:
        content = page_content(sheet, h, paper_left_in, play_in)
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content))
        objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] /Contents %d 0 R "
                       b"/Resources << /Font << /F1 3 0 R >> /ExtGState << /GS1 4 0 R >> >> >>"
                       % (w, h, len(objects)))
        kids.append(len(objects))
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % k for k in kids), len(kids))

    data = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for n, obj in enumerate(objects, start=1):
        offsets.append(len(data))
        data += b"%d 0 obj\n%s\nendobj\n" % (n, obj)
    xref = len(data)
    data += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    data += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    data += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    Path(path).write_bytes(bytes(data))
