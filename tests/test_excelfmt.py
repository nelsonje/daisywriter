import datetime as dt

import pytest

from daisywriter.excelfmt import format_excel

D = dt.datetime(2026, 10, 4, 14, 5, 9)

CASES = [
    # numbers
    (89.5, '"$"#,##0.00', "$89.50"),
    (1234567.891, "#,##0.00", "1,234,567.89"),
    (-1234.5, '"$"#,##0.00_);[Red]\\("$"#,##0.00\\)', "($1,234.50)"),
    (-3, "0", "-3"),
    (0.256, "0.0%", "25.6%"),
    (2134, "00000", "02134"),
    (5551234567, "(###) ###-####", "(555) 123-4567"),
    (123456789, "000-00-0000", "123-45-6789"),
    (0.5, "#.00", ".50"),
    (12.5, "0.##", "12.5"),
    (12, "0.##", "12."),
    (1500000, '#,##0,,"M"', "2M"),
    (1500000, '#,##0.0,,"M"', "1.5M"),
    (89.5, "[$€-x-euro2] #,##0.00", "€ 89.50"),
    (12345.678, "0.00E+00", "1.23E+04"),
    # Accounting (openpyxl's built-in 44 lacks its ";" separators)
    (89.5, '_("$"* #,##0.00_)_("$"* \\(#,##0.00\\)_("$"* "-"??_)_(@_)', "$89.50"),
    (-89.5, '_("$"* #,##0.00_);_("$"* \\(#,##0.00\\);_("$"* "-"??_);_(@_)', "$(89.50)"),
    (0, '_("$"* #,##0.00_);_("$"* \\(#,##0.00\\);_("$"* "-"??_);_(@_)', "$-"),
    # conditions
    (150, '[>=100]"big";[<0]"neg";"small"', "big"),
    (5, '[>=100]"big";[<0]"neg";"small"', "small"),
    # dates and times
    (D, "mmmm d, yyyy", "October 4, 2026"),
    (D, "mm-dd-yy", "10/4/2026"),  # built-in 14: Excel shows the regional short date
    (D, "[$-409]dddd, mmmm dd, yyyy;@", "Sunday, October 04, 2026"),
    (D, "d-mmm-yy", "4-Oct-26"),
    (D, "yyyy-mm-dd", "2026-10-04"),
    (D, "h:mm AM/PM", "2:05 PM"),
    (D, "hh:mm:ss", "14:05:09"),
    (D, "mmm d \\a\\t h:mm a/p", "Oct 4 at 2:05 p"),
    (D, "mmmmm", "O"),
    (46299.5, "m/d/yyyy h:mm", "10/4/2026 12:00"),  # a date serial number
    (dt.date(2026, 1, 2), "dd.mm.yyyy", "02.01.2026"),
    # text
    ("Smith", '"Attn: "@', "Attn: Smith"),
    ("x", '0.00;-0.00;0;"<"@">"', "<x>"),
]


@pytest.mark.parametrize("value,fmt,expected", CASES)
def test_format_excel(value, fmt, expected):
    assert format_excel(value, fmt) == expected


@pytest.mark.parametrize("value,fmt", [
    (89.5, "General"), (89.5, None), ("text", "General"), ("text", "0.00"),
    (0.75, "# ?/?"), (True, "0"), (42, "@"),
])
def test_default_formatting_is_used(value, fmt):
    assert format_excel(value, fmt) is None
