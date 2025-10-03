from datetime import date
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.time_expression_parser import parse_time_expression


@pytest.mark.parametrize(
    "expression, today, expected",
    [
        (
            "last month",
            date(2025, 10, 2),
            {
                "start_date": "2025-09-01",
                "end_date": "2025-10-01",
                "chips": "Sep 1 → Oct 1 (exclusive)",
            },
        ),
        (
            "Q1 2024",
            date(2025, 10, 2),
            {
                "start_date": "2024-01-01",
                "end_date": "2024-04-01",
                "chips": "Q1 2024 = Jan 1 → Apr 1 (exclusive)",
            },
        ),
        (
            "last 8 weeks",
            date(2025, 10, 2),
            {
                "start_date": "2025-08-07",
                "end_date": "2025-10-02",
                "chips": "Aug 7 → Oct 2 (exclusive)",
            },
        ),
        (
            "since Jan 15",
            date(2025, 10, 2),
            {
                "start_date": "2025-01-15",
                "end_date": "2025-10-02",
                "chips": "Jan 15 → Oct 2 (exclusive)",
            },
        ),
        (
            "2023",
            date(2025, 10, 2),
            {
                "start_date": "2023-01-01",
                "end_date": "2024-01-01",
                "chips": "2023 = Jan 1 → Jan 1 (exclusive)",
            },
        ),
        (
            "2024-06",
            date(2025, 10, 2),
            {
                "start_date": "2024-06-01",
                "end_date": "2024-07-01",
                "chips": "2024-06 = Jun 1 → Jul 1 (exclusive)",
            },
        ),
    ],
)
def test_parse_time_expression(expression, today, expected):
    result = parse_time_expression(expression, today=today)
    assert result["expression"] == expression
    assert result["start_date"] == expected["start_date"]
    assert result["end_date"] == expected["end_date"]
    assert result["chips"] == expected["chips"]


@pytest.mark.parametrize(
    "expression",
    ["", "   ", "next decade"],
)
def test_parse_time_expression_invalid(expression):
    with pytest.raises(ValueError):
        parse_time_expression(expression, today=date(2025, 10, 2))
