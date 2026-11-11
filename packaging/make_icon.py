"""Draw the daisywriter icon: a daisywheel on a sheet of paper.

Renders PNGs at the sizes Windows uses and packs them into an .ico:
    uv run python packaging/make_icon.py
writes src/daisywriter/gui/icons/daisywriter-<size>.png (the window icon),
packaging/daisywriter.ico (the Windows programs, the Start menu and Settings >
Apps) and, on macOS, packaging/daisywriter.icns (the Mac app).
Small sizes get fewer, thicker petals, so they stay readable.
"""
from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPen

ROOT = Path(__file__).resolve().parent.parent
SIZES = [16, 24, 32, 48, 64, 128, 256]
PAPER_TOP, PAPER_BOTTOM, PAPER_EDGE = QColor("#fdf8ec"), QColor("#efe2c2"), QColor("#a8946a")
INK, HUB, HUB_RING, HOLE = QColor("#22252b"), QColor("#c8362b"), QColor("#8e2219"), QColor("#fdf8ec")


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    s = float(size)
    c = QPointF(s / 2, s / 2)

    # the paper: a rounded tile
    m = s * 0.03
    tile = QRectF(m, m, s - 2 * m, s - 2 * m)
    grad = QLinearGradient(tile.topLeft(), tile.bottomLeft())
    grad.setColorAt(0, PAPER_TOP)
    grad.setColorAt(1, PAPER_BOTTOM)
    p.setBrush(grad)
    p.setPen(QPen(PAPER_EDGE, max(1.0, s / 96)))
    p.drawRoundedRect(tile, s * 0.18, s * 0.18)

    # the petals: spokes from the hub, each ending in a pad
    petals = 20 if size >= 64 else 12 if size >= 32 else 8
    reach = s * 0.40  # centre of the pads
    pad = s * (0.050 if size >= 64 else 0.075 if size >= 32 else 0.09)
    spoke = s * (0.022 if size >= 64 else 0.05 if size >= 32 else 0.07)
    hub = s * 0.15
    pen = QPen(INK, spoke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    for i in range(petals):
        a = 2 * math.pi * i / petals - math.pi / 2
        tip = QPointF(c.x() + reach * math.cos(a), c.y() + reach * math.sin(a))
        p.setPen(pen)
        p.drawLine(c, tip)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(INK)
        p.drawEllipse(tip, pad, pad)

    # the hub, red like the other half of a two-colour ribbon
    p.setPen(QPen(HUB_RING, max(1.0, s * 0.02)))
    p.setBrush(HUB)
    p.drawEllipse(c, hub, hub)
    if size >= 24:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(HOLE)
        p.drawEllipse(c, hub * 0.32, hub * 0.32)
    p.end()
    return img


def draw_mac(size: int) -> QImage:
    """macOS icons leave a margin around the artwork (Apple's grid puts the tile
    at about 80 % of the canvas), or the icon looks too big in the Dock."""
    inner = round(size * 0.84)
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.drawImage((size - inner) // 2, (size - inner) // 2, draw(inner))
    p.end()
    return img


def write_icns(path: Path) -> bool:
    """A macOS .icns, with Apple's iconutil (macOS only)."""
    iconutil = shutil.which("iconutil")
    if not iconutil:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "daisywriter.iconset"
        iconset.mkdir()
        for base in (16, 32, 128, 256, 512):
            for scale, suffix in ((1, ""), (2, "@2x")):
                (iconset / f"icon_{base}x{base}{suffix}.png").write_bytes(png_bytes(draw_mac(base * scale)))
        subprocess.run([iconutil, "-c", "icns", str(iconset), "-o", str(path)], check=True)
    return True


def png_bytes(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def write_ico(path: Path, images: dict[int, bytes]):
    """An .ico holding PNG images (supported since Windows Vista)."""
    head = struct.pack("<HHH", 0, 1, len(images))
    entries, data = b"", b""
    offset = 6 + 16 * len(images)
    for size, png in sorted(images.items()):
        dim = 0 if size >= 256 else size  # 0 means 256
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    path.write_bytes(head + entries + data)


def main() -> int:
    QGuiApplication.instance() or QGuiApplication(sys.argv)
    icons = ROOT / "src" / "daisywriter" / "gui" / "icons"
    icons.mkdir(exist_ok=True)
    images = {}
    for size in SIZES:
        png = png_bytes(draw(size))
        images[size] = png
        if size in (16, 32, 48, 256):
            (icons / f"daisywriter-{size}.png").write_bytes(png)
    write_ico(ROOT / "packaging" / "daisywriter.ico", images)
    print(f"wrote {icons} and packaging/daisywriter.ico")
    if write_icns(ROOT / "packaging" / "daisywriter.icns"):
        print("wrote packaging/daisywriter.icns")
    else:
        print("skipped packaging/daisywriter.icns (needs macOS's iconutil)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
