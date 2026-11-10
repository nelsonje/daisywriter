from daisywriter.layout import Cell
from daisywriter.preview import _ansi_line, _html_cells, _plain_line


def test_strikethrough_in_previews():
    cells = [Cell("a"), Cell("b", strike=True), Cell("c", strike=True)]
    assert _plain_line(cells, 5) == ["ab̶c̶  "]
    assert _ansi_line(cells, 3) == "a\x1b[0m\x1b[9mbc\x1b[0m"
    assert _html_cells(cells) == "a<s>bc</s>"
