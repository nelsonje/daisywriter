import datetime as dt

from daisywriter.model import FieldRef
from daisywriter.values import format_date, format_number, format_value, is_date_picture


def ref(picture=None, kind=None, case=None, **kw):
    return FieldRef("X", picture, kind, case, **kw)


def test_date_pictures():
    d = dt.datetime(2026, 3, 5, 14, 7)
    assert format_date(d, "MMMM d, yyyy") == "March 5, 2026"
    assert format_date(d, "dddd, d MMM yy") == "Thursday, 5 Mar 26"
    assert format_date(d, "MM/dd/yyyy") == "03/05/2026"
    assert format_date(d, "h:mm AM/PM") == "2:07 PM"
    assert format_date(d, "'Week of' MMMM d") == "Week of March 5"


def test_number_pictures():
    assert format_number(1234.5, "$#,##0.00") == "$1,234.50"
    assert format_number(-3.14159, "0.0") == "-3.1"
    assert format_number(0.256, "0%") == "26%"
    assert format_number(7, "#") == "7"


def test_default_formats():
    assert format_value(dt.datetime(2026, 11, 8), ref())[0] == "November 8, 2026"
    assert format_value(42.0, ref())[0] == "42"
    assert format_value(0.1 + 0.2, ref())[0] == "0.3"
    assert format_value("  padded  ", ref())[0] == "padded"
    assert format_value(None, ref())[0] == ""


def test_placeholder_picture_decided_by_value():
    assert format_value(dt.date(2026, 1, 2), ref("MMM d"))[0] == "Jan 2"
    assert format_value(1500, ref("#,##0"))[0] == "1,500"
    assert format_value("2026-07-04", ref("MMMM d, yyyy"))[0] == "July 4, 2026"


def test_picture_mismatch_is_reported():
    text, problem = format_value("next week", ref("MMMM d"))
    assert text == "next week" and "isn't a date" in problem
    text, problem = format_value(12, ref("MMMM d", kind="date"))
    assert text == "12" and problem


def test_case_and_before_after():
    assert format_value("smith", ref(case="upper"))[0] == "SMITH"
    assert format_value("mary ann", ref(case="caps"))[0] == "Mary Ann"
    assert format_value("Apt 4", ref(before=", "))[0] == ", Apt 4"
    assert format_value("", ref(before=", "))[0] == ""


def test_is_date_picture():
    assert is_date_picture("MMMM d, yyyy")
    assert not is_date_picture("$#,##0.00")
    assert not is_date_picture("upper")
