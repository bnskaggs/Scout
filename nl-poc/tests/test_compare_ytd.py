"""Test YTD comparison parsing and multi-year ranges."""
import sys
from datetime import date
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.time_utils import extract_time_range, parse_year, parse_relative_range


def test_ytd_with_explicit_year():
    """Test that '2024 YTD' extracts year correctly."""
    today = date(2025, 9, 30)

    # Test "2024 YTD" - should be Jan 1 2024 to Sept 1 2024 (same month as today)
    result = parse_relative_range("incidents in 2024 YTD", today=today)
    assert result is not None
    assert result.start == date(2024, 1, 1)
    assert result.end == date(2024, 10, 1)  # Next month after Sept
    assert result.label == "2024 YTD"


def test_ytd_current_year():
    """Test that 'YTD' without year defaults to current year."""
    today = date(2025, 9, 30)

    result = parse_relative_range("YTD incidents", today=today)
    assert result is not None
    assert result.start == date(2025, 1, 1)
    assert result.end == date(2025, 10, 1)  # Next month after current month
    assert result.label == "2025 YTD"


def test_multi_year_range_with_ytd():
    """Test '2023 vs 2024 YTD' creates combined range."""
    today = date(2025, 9, 30)

    # This should create a range from 2023-01-01 to 2024-10-01
    result = parse_year("Compare assaults in 2023 vs 2024 YTD")
    assert result is not None
    assert result.start == date(2023, 1, 1)
    assert result.end == date(2024, 10, 1)  # YTD end for 2024
    assert "2023 vs 2024 YTD" in result.label


def test_multi_year_range_without_ytd():
    """Test '2023 and 2024' creates full two-year range."""
    result = parse_year("Trend of burglaries from 2023 and 2024")
    assert result is not None
    assert result.start == date(2023, 1, 1)
    assert result.end == date(2024, 12, 31)  # Full 2024
    assert "2023-2024" in result.label or "2023" in result.label


def test_extract_time_range_with_ytd():
    """Test full extraction with YTD patterns."""
    today = date(2025, 9, 30)

    # Should extract the multi-year YTD range
    result = extract_time_range("Compare assaults in 2023 vs 2024 YTD", today=today)
    assert result is not None, "extract_time_range returned None"
    assert result.start == date(2023, 1, 1), f"Expected start 2023-01-01, got {result.start}"
    assert result.end == date(2024, 10, 1), f"Expected end 2024-10-01, got {result.end}"


def test_single_year():
    """Test that single year still works correctly."""
    result = parse_year("incidents in 2023")
    assert result is not None
    assert result.start == date(2023, 1, 1)
    assert result.end == date(2023, 12, 31)
    assert result.label == "2023"


if __name__ == "__main__":
    tests = [
        test_ytd_with_explicit_year,
        test_ytd_current_year,
        test_multi_year_range_with_ytd,
        test_multi_year_range_without_ytd,
        test_extract_time_range_with_ytd,
        test_single_year,
    ]
    for test in tests:
        try:
            test()
            print(f"PASS: {test.__name__}")
        except AssertionError as e:
            print(f"FAIL: {test.__name__}: {e}")
        except Exception as e:
            print(f"ERROR: {test.__name__}: {type(e).__name__}: {e}")
