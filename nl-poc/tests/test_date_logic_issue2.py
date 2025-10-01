"""Test date logic for Issue #2."""
import sys
from datetime import date
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.time_utils import extract_time_range, parse_relative_range


def test_ytd_current_year():
    """Test that YTD uses current year (2025 when running in Oct 2025)."""
    # Mock today as October 15, 2025
    today = date(2025, 10, 15)

    result = parse_relative_range("year to date", today=today)

    print(f"Query: 'year to date'")
    print(f"Today (mocked): {today}")
    print(f"Result: start={result.start}, end={result.end}, label={result.label}")

    assert result.start == date(2025, 1, 1), f"Expected start 2025-01-01, got {result.start}"
    assert result.end == date(2025, 11, 1), f"Expected end 2025-11-01 (next month after Oct), got {result.end}"
    assert result.label == "2025 YTD"

    print("PASS: YTD uses current year (2025)")


def test_last_year_range():
    """Test that 'last year' returns trailing 12 months."""
    # Mock today as October 15, 2025
    today = date(2025, 10, 15)

    result = parse_relative_range("last year", today=today)

    print(f"\nQuery: 'last year'")
    print(f"Today (mocked): {today}")
    print(f"Result: start={result.start}, end={result.end}, label={result.label}")

    # "last year" should mean trailing 12 months
    # According to issue: should be Oct 2024 to Oct 2025
    # That means: start from same month last year, through next month after current
    expected_start = date(2024, 10, 1)  # Same month, last year
    expected_end = date(2025, 11, 1)    # Next month after current (for exclusive upper bound)

    print(f"Expected: start={expected_start}, end={expected_end}")

    assert result.start == expected_start, f"Expected start {expected_start}, got {result.start}"
    assert result.end == expected_end, f"Expected end {expected_end}, got {result.end}"

    print("PASS: Last year returns Oct 2024 to Nov 2025")


def test_last_year_from_extract():
    """Test last year through full extraction."""
    today = date(2025, 10, 15)

    result = extract_time_range("incidents over the last year", today=today)

    print(f"\nQuery: 'incidents over the last year'")
    print(f"Today (mocked): {today}")
    print(f"Result: start={result.start}, end={result.end}, label={result.label}")

    # Should be trailing 12 months
    expected_start = date(2024, 10, 1)
    expected_end = date(2025, 11, 1)

    assert result.start == expected_start, f"Expected start {expected_start}, got {result.start}"
    assert result.end == expected_end, f"Expected end {expected_end}, got {result.end}"

    print("PASS: 'over the last year' works correctly")


def test_ytd_extract():
    """Test YTD through full extraction."""
    today = date(2025, 10, 15)

    result = extract_time_range("incidents by area year to date", today=today)

    print(f"\nQuery: 'incidents by area year to date'")
    print(f"Today (mocked): {today}")
    print(f"Result: start={result.start}, end={result.end}, label={result.label}")

    assert result.start == date(2025, 1, 1)
    assert result.end == date(2025, 11, 1)
    assert "2025" in result.label

    print("PASS: 'year to date' through extraction works correctly")


if __name__ == "__main__":
    try:
        test_ytd_current_year()
        test_last_year_range()
        test_last_year_from_extract()
        test_ytd_extract()
        print("\n" + "="*60)
        print("ALL TESTS PASSED!")
        print("="*60)
    except AssertionError as e:
        print(f"\nFAIL: {e}")
        import traceback
        traceback.print_exc()
