from datetime import date
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.time_utils import TimeRange, extract_time_range


@pytest.mark.parametrize(
    "text, today, expected_start, expected_end",
    [
        ("How many stabbings happened in March 2023?", date(2025, 10, 5), date(2023, 3, 1), date(2023, 4, 1)),
        ("Incidents in Q1 2024", date(2025, 10, 5), date(2024, 1, 1), date(2024, 4, 1)),
        ("Trends for 2024-06", date(2025, 10, 5), date(2024, 6, 1), date(2024, 7, 1)),
        ("Report for 2023", date(2025, 10, 5), date(2023, 1, 1), date(2024, 1, 1)),
    ],
)
def test_extract_time_range_exclusive(text, today, expected_start, expected_end):
    result = extract_time_range(text, today=today)
    assert isinstance(result, TimeRange)
    assert result.start == expected_start
    assert result.end == expected_end
    assert result.exclusive_end is True
