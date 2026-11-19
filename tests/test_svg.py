"""Emulated sheets as SVG."""
from daisywriter.svg import sheet_svg
from daisywriter.transports.emulator import Sheet, Strike


def test_strikes_where_the_typewriter_puts_them():
    sheet = Sheet(1, 132, [Strike(60, 12, "A", False), Strike(66, 12, "<", True), Strike(60, 12, "A", False),
                           Strike(72, 12, " ", False), Strike(60, 120, "Z", False)])
    svg = sheet_svg(sheet, play_in=0.0)
    assert 'viewBox="0 0 612 792"' in svg
    assert svg.count('<text x="72.00" y="72.00">A</text>') == 2  # an overstrike: drawn twice, darker
    assert '<text x="79.20" y="72.00">&lt;</text>' in svg and ">Z<" in svg and "> <" not in svg
    part = sheet_svg(sheet, top_in=0.5, bottom_in=2, left_in=0.5, right_in=8, title="Top & left")
    assert 'viewBox="36 36 540 108"' in part and ">Z<" not in part and 'aria-label="Top &amp; left"' in part
