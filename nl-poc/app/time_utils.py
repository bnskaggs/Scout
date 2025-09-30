"""Utilities for parsing and normalising time phrases."""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional


@dataclass
class TimeRange:
    start: date
    end: date
    label: str
    op: str = "between"

    def to_filter(self) -> dict:
        if self.op == "=":
            return {
                "field": "month",
                "op": "=",
                "value": self.start.isoformat(),
            }
        return {
            "field": "month",
            "op": "between",
            "value": [self.start.isoformat(), self.end.isoformat()],
        }


_QUARTER_PATTERN = re.compile(
    r"\b(?:q([1-4])\s*([12]\d{3})|([12]\d{3})\s*[-\/]?\s*q([1-4]))\b",
    re.IGNORECASE,
)
_MONTH_PATTERN = re.compile(r"(20\d{2})[-/](0[1-9]|1[0-2])")
_YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")


def _start_of_month(year: int, month: int) -> date:
    return date(year, month, 1)


def _end_of_month(year: int, month: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day)


def _next_month(dt: date) -> date:
    if dt.month == 12:
        return date(dt.year + 1, 1, 1)
    return date(dt.year, dt.month + 1, 1)


def current_date() -> date:
    return date.today()


def current_month_start(today: Optional[date] = None) -> date:
    today = today or current_date()
    return date(today.year, today.month, 1)


def previous_month_start(today: Optional[date] = None) -> date:
    start = current_month_start(today)
    anchor = start - timedelta(days=1)
    return date(anchor.year, anchor.month, 1)


def _shift_month(start: date, delta: int) -> date:
    year = start.year + ((start.month - 1 + delta) // 12)
    month = (start.month - 1 + delta) % 12 + 1
    return date(year, month, 1)


def parse_relative_range(text: str, today: Optional[date] = None) -> Optional[TimeRange]:
    today = today or current_date()
    text_l = text.lower()
    if "ytd" in text_l or "year to date" in text_l or "this year to date" in text_l:
        start = date(today.year, 1, 1)
        end = _next_month(current_month_start(today))
        return TimeRange(start=start, end=end, label=f"{today.year} YTD")
    trailing_year_phrases = (
        "last year",
        "past year",
        "over the last year",
        "over last year",
        "last 12 months",
        "past 12 months",
    )
    if any(phrase in text_l for phrase in trailing_year_phrases):
        anchor = current_month_start(today)
        start = _shift_month(anchor, -11)
        end = _next_month(anchor)
        return TimeRange(start=start, end=end, label="Last 12 months")
    if "this year" in text_l:
        start = date(today.year, 1, 1)
        end = date(today.year, 12, 31)
        return TimeRange(start=start, end=end, label=f"{today.year}")
    if "this month" in text_l:
        start = current_month_start(today)
        return TimeRange(start=start, end=start, label=start.strftime("%Y-%m"), op="=")
    if "last month" in text_l:
        start = previous_month_start(today)
        return TimeRange(start=start, end=start, label=start.strftime("%Y-%m"), op="=")
    if "last 3 months" in text_l or "last three months" in text_l:
        end = current_month_start(today)
        start = _shift_month(previous_month_start(today), -2)
        return TimeRange(start=start, end=end, label="Last 3 months")
    if "last quarter" in text_l:
        quarter = (today.month - 1) // 3
        if quarter == 0:
            year = today.year - 1
            quarter = 4
        else:
            year = today.year
        start_month = (quarter - 1) * 3 + 1
        start = date(year, start_month, 1)
        end = date(year, start_month + 2, calendar.monthrange(year, start_month + 2)[1])
        return TimeRange(start=start, end=_next_month(end.replace(day=1)), label=f"Q{quarter} {year}")
    return None


def parse_quarter(text: str) -> Optional[TimeRange]:
    match = _QUARTER_PATTERN.search(text)
    if not match:
        return None
    if match.group(1) and match.group(2):
        q = int(match.group(1))
        year = int(match.group(2))
    else:
        year = int(match.group(3))
        q = int(match.group(4))
    start_month = (q - 1) * 3 + 1
    start = date(year, start_month, 1)
    end_month = start_month + 2
    end = date(year, end_month, 1)
    return TimeRange(start=start, end=_next_month(end), label=f"Q{q} {year}")


def parse_month(text: str) -> Optional[TimeRange]:
    match = _MONTH_PATTERN.search(text)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        start = date(year, month, 1)
        return TimeRange(start=start, end=start, label=start.strftime("%Y-%m"), op="=")
    return None


def parse_year(text: str) -> Optional[TimeRange]:
    matches = list(_YEAR_PATTERN.finditer(text))
    if not matches:
        return None
    # prefer the last occurrence to capture more specific context like "in 2023"
    year = int(matches[-1].group(1))
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    return TimeRange(start=start, end=end, label=str(year))


def extract_time_range(text: str, today: Optional[date] = None) -> Optional[TimeRange]:
    today = today or current_date()
    for parser in (parse_month, parse_quarter, parse_relative_range, parse_year):
        result = parser(text)
        if result:
            return result
    return None


def describe_time_range(time_range: Optional[TimeRange]) -> str:
    if not time_range:
        return "All available time"
    if time_range.label:
        return time_range.label
    start = time_range.start.strftime("%Y-%m")
    end = (time_range.end - timedelta(days=1)).strftime("%Y-%m")
    if start == end:
        return start
    return f"{start} to {end}"
