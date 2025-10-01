"""Test change_pct formatting."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.main import _format_change_pct


def test_format_change_pct_positive():
    """Test formatting positive change percentages."""
    records = [
        {"crime_type": "Assault", "incidents": 150, "change_pct": 0.156789},
        {"crime_type": "Burglary", "incidents": 80, "change_pct": 0.0234},
    ]

    formatted = _format_change_pct(records)

    assert formatted[0]["change_pct_formatted"] == "+15.68%"
    assert formatted[1]["change_pct_formatted"] == "+2.34%"
    # Raw values preserved
    assert formatted[0]["change_pct"] == 0.156789
    assert formatted[1]["change_pct"] == 0.0234
    print("PASS: Positive percentages formatted correctly")


def test_format_change_pct_negative():
    """Test formatting negative change percentages."""
    records = [
        {"crime_type": "Theft", "incidents": 200, "change_pct": -0.0234},
        {"crime_type": "Robbery", "incidents": 100, "change_pct": -0.1567},
    ]

    formatted = _format_change_pct(records)

    assert formatted[0]["change_pct_formatted"] == "-2.34%"
    assert formatted[1]["change_pct_formatted"] == "-15.67%"
    print("PASS: Negative percentages formatted correctly")


def test_format_change_pct_null():
    """Test handling null change_pct values."""
    records = [
        {"crime_type": "Vandalism", "incidents": 50, "change_pct": None},
    ]

    formatted = _format_change_pct(records)

    assert formatted[0]["change_pct_formatted"] == "N/A"
    assert formatted[0]["change_pct"] is None
    print("PASS: Null values handled correctly")


def test_format_change_pct_zero():
    """Test formatting zero change."""
    records = [
        {"crime_type": "Arson", "incidents": 10, "change_pct": 0.0},
    ]

    formatted = _format_change_pct(records)

    assert formatted[0]["change_pct_formatted"] == "+0.00%"
    assert formatted[0]["change_pct"] == 0.0
    print("PASS: Zero change formatted correctly")


def test_format_change_pct_no_change_column():
    """Test records without change_pct column are returned unchanged."""
    records = [
        {"crime_type": "Assault", "incidents": 150},
    ]

    formatted = _format_change_pct(records)

    assert formatted == records
    assert "change_pct_formatted" not in formatted[0]
    print("PASS: Records without change_pct returned unchanged")


def test_format_change_pct_rounding():
    """Test rounding to 2 decimal places."""
    records = [
        {"crime_type": "Test1", "incidents": 100, "change_pct": 0.123456},  # 12.35%
        {"crime_type": "Test2", "incidents": 100, "change_pct": 0.125},     # 12.50%
        {"crime_type": "Test3", "incidents": 100, "change_pct": -0.999},    # -99.90%
    ]

    formatted = _format_change_pct(records)

    assert formatted[0]["change_pct_formatted"] == "+12.35%"
    assert formatted[1]["change_pct_formatted"] == "+12.50%"
    assert formatted[2]["change_pct_formatted"] == "-99.90%"
    print("PASS: Rounding to 2 decimals works correctly")


if __name__ == "__main__":
    test_format_change_pct_positive()
    test_format_change_pct_negative()
    test_format_change_pct_null()
    test_format_change_pct_zero()
    test_format_change_pct_no_change_column()
    test_format_change_pct_rounding()
    print("\nAll tests passed!")
