from datetime import date

from app.time_utils import TimeRange, parse_relative_range


def test_parse_relative_range_past_nine_months():
    today = date(2024, 3, 15)
    result = parse_relative_range("incidents in the past 9 months", today=today)

    assert isinstance(result, TimeRange)
    assert result.start == date(2023, 6, 1)
    assert result.end == date(2024, 3, 1)
    assert result.label == "Past 9 months"
