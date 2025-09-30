from datetime import date as real_date, datetime as real_datetime

import pytest

import app.time_utils as time_utils


def test_current_date_uses_timezone_when_available(monkeypatch):
    if time_utils.ZoneInfo is None:
        pytest.skip("zoneinfo module is not available")

    tz = time_utils.ZoneInfo("America/Chicago")

    class DummyDateTime:
        @classmethod
        def now(cls, tz_arg):
            assert tz_arg == tz
            return real_datetime(2024, 5, 2, 12, 0, tzinfo=tz)

    monkeypatch.setattr(time_utils, "datetime", DummyDateTime)
    monkeypatch.setattr(time_utils, "ZoneInfo", lambda name: tz)

    assert time_utils.current_date() == real_date(2024, 5, 2)


def test_current_date_falls_back_without_zoneinfo(monkeypatch):
    expected = real_date(2024, 5, 3)

    class DummyDate:
        @classmethod
        def today(cls):
            return expected

    monkeypatch.setattr(time_utils, "ZoneInfo", None)
    monkeypatch.setattr(time_utils, "date", DummyDate)

    assert time_utils.current_date() is expected


def test_current_month_start_with_explicit_today():
    today = real_date(2024, 6, 18)
    assert time_utils.current_month_start(today) == real_date(2024, 6, 1)


def test_previous_month_start_with_explicit_today():
    today = real_date(2024, 1, 15)
    assert time_utils.previous_month_start(today) == real_date(2023, 12, 1)


def test_parse_relative_range_last_twelve_months():
    today = real_date(2024, 8, 20)
    result = time_utils.parse_relative_range("show last 12 months", today=today)
    assert result is not None
    assert result.start == real_date(2023, 9, 1)
    assert result.end == real_date(2024, 9, 1)


def test_extract_time_range_this_month_with_today():
    today = real_date(2024, 11, 5)
    time_range = time_utils.extract_time_range("this month", today=today)
    assert time_range is not None
    assert time_range.start == real_date(2024, 11, 1)
    assert time_range.end == real_date(2024, 11, 1)
