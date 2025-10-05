"""Utilities for parsing and normalising time phrases."""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from zoneinfo import ZoneInfo


@dataclass
class TimeRange:
    start: date
    end: date
    label: str
    op: str = "between"
    exclusive_end: bool = True

    def to_filter(self) -> dict:
        return {
            "field": "month",
            "op": "between",
            "value": [self.start.isoformat(), self.end.isoformat()],
            "exclusive_end": self.exclusive_end,
        }


_QUARTER_PATTERN = re.compile(
    r"\b(?:q([1-4])\s*([12]\d{3})|([12]\d{3})\s*[-\/]?\s*q([1-4]))\b",
    re.IGNORECASE,
)
_ISO_MONTH_PATTERN = re.compile(r"(20\d{2})[-/](0[1-9]|1[0-2])")
_MONTH_NAME_PATTERN = re.compile(
    r"\b(?P<month>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(?P<year>20\d{2})\b",
    re.IGNORECASE,
)
_YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")
_RELATIVE_MONTHS_PATTERN = re.compile(
    r"\b(?P<keyword>past|last)\s+(?P<count>\d{1,2})\s+months?\b",
    re.IGNORECASE,
)

_CHICAGO_TZ = ZoneInfo("America/Chicago")


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
    today = datetime.now(_CHICAGO_TZ).date()
    print(f"[TIME_UTILS DEBUG] current_date() returning: {today}")
    return today


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
        # Check for multi-year YTD patterns like "2023 vs 2024 YTD" first
        multi_year_ytd = re.search(
            r'\b(20\d{2})\s*(?:vs\.?|and|to|through|-)\s*(20\d{2})\s+ytd\b',
            text_l
        )
        if multi_year_ytd:
            year1 = int(multi_year_ytd.group(1))
            year2 = int(multi_year_ytd.group(2))
            start_year = min(year1, year2)
            end_year = max(year1, year2)
            start = date(start_year, 1, 1)
            # YTD for the end year
            if end_year == today.year:
                end = _next_month(current_month_start(today))
            else:
                end = _next_month(date(end_year, min(today.month, 12), 1))
            return TimeRange(start=start, end=end, label=f"{start_year} vs {end_year} YTD")

        # Check for explicit year in "YYYY YTD" pattern
        ytd_year_match = re.search(r'\b(20\d{2})\s+ytd\b', text_l)
        if ytd_year_match:
            year = int(ytd_year_match.group(1))
            start = date(year, 1, 1)
            # If year is current year, use current month; otherwise use end of year
            if year == today.year:
                end = _next_month(current_month_start(today))
            else:
                # For past years, YTD means through the same month of that year
                # For future years or completed years, through end of year
                if year < today.year:
                    # Use same month as today, but in that year
                    end = _next_month(date(year, min(today.month, 12), 1))
                else:
                    end = _next_month(date(year, 12, 1))
            return TimeRange(start=start, end=end, label=f"{year} YTD")
        # Default: current year YTD
        start = date(today.year, 1, 1)
        end = _next_month(current_month_start(today))
        return TimeRange(start=start, end=end, label=f"{today.year} YTD")
    month_window_match = re.search(r"\b(last|past)\s+(6|9|12)\s+months?\b", text_l)
    if month_window_match:
        qualifier, months_str = month_window_match.groups()
        months = int(months_str)
        anchor = current_month_start(today)
        if qualifier == "past":
            end = anchor
            if today == _end_of_month(today.year, today.month):
                end = _next_month(anchor)
            start = _shift_month(end, -months)
            label_prefix = "Past"
        else:
            end = anchor
            start = _shift_month(end, -months)
            label_prefix = "Last"
        return TimeRange(start=start, end=end, label=f"{label_prefix} {months} months")
    trailing_year_phrases = (
        "last year",
        "past year",
        "over the last year",
        "over last year",
    )
    if any(phrase in text_l for phrase in trailing_year_phrases):
        anchor = current_month_start(today)
        start = _shift_month(anchor, -12)  # Go back 12 months (same month last year)
        end = _next_month(anchor)
        return TimeRange(start=start, end=end, label="Last 12 months")
    if "this year" in text_l:
        start = date(today.year, 1, 1)
        end = date(today.year + 1, 1, 1)
        return TimeRange(start=start, end=end, label=f"{today.year}")
    if "this month" in text_l:
        start = current_month_start(today)
        end = _next_month(start)
        return TimeRange(start=start, end=end, label=start.strftime("%Y-%m"))
    if "last month" in text_l:
        start = previous_month_start(today)
        end = current_month_start(today)
        return TimeRange(start=start, end=end, label=start.strftime("%Y-%m"))
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
    match = _RELATIVE_MONTHS_PATTERN.search(text_l)
    if match:
        count = int(match.group("count"))
        if count <= 0:
            return None
        keyword = match.group("keyword").lower()
        anchor = current_month_start(today)
        if keyword == "last":
            end = current_month_start(today)
            start = _shift_month(previous_month_start(today), -(count - 1))
            label = f"Last {count} months"
        else:
            start = _shift_month(anchor, -(count - 1))
            end = _next_month(anchor)
            label = f"Past {count} months"
        return TimeRange(start=start, end=end, label=label)
    return None


def trailing_year_range(today: Optional[date] = None) -> TimeRange:
    """Return a time range covering the trailing 12 months."""

    today = today or current_date()
    anchor = current_month_start(today)
    start = _shift_month(anchor, -12)  # Go back 12 months (same month last year)
    end = _next_month(anchor)
    return TimeRange(start=start, end=end, label="Last 12 months")


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


_MONTH_NAME_LOOKUP = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def parse_month(text: str) -> Optional[TimeRange]:
    match = _ISO_MONTH_PATTERN.search(text)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        start = date(year, month, 1)
        end = _next_month(start)
        return TimeRange(start=start, end=end, label=start.strftime("%Y-%m"))

    match = _MONTH_NAME_PATTERN.search(text)
    if match:
        month_token = match.group("month")
        year = int(match.group("year"))
        key = month_token[:3].lower()
        month = _MONTH_NAME_LOOKUP[key]
        start = date(year, month, 1)
        end = _next_month(start)
        return TimeRange(start=start, end=end, label=start.strftime("%Y-%m"))
    return None


def parse_year(text: str) -> Optional[TimeRange]:
    matches = list(_YEAR_PATTERN.finditer(text))
    if not matches:
        return None

    # Check for multi-year patterns like "2023 vs 2024" or "2023 and 2024"
    if len(matches) >= 2:
        years = [int(m.group(1)) for m in matches]
        # Look for "vs", "and", "to" between years
        multi_year_pattern = re.search(
            r'\b(20\d{2})\s*(?:vs\.?|and|to|through|-)\s*(20\d{2})\b',
            text,
            re.IGNORECASE
        )
        if multi_year_pattern:
            year1 = int(multi_year_pattern.group(1))
            year2 = int(multi_year_pattern.group(2))
            start_year = min(year1, year2)
            end_year = max(year1, year2)
            start = date(start_year, 1, 1)

            # Check if second year has YTD qualifier
            ytd_after = re.search(
                rf'\b{end_year}\s+ytd\b',
                text.lower()
            )
            if ytd_after:
                # End at next month of current month in end_year
                today = current_date()
                end = _next_month(date(end_year, min(today.month, 12), 1))
            else:
                end = date(end_year + 1, 1, 1)

            label = f"{start_year}-{end_year}" if not ytd_after else f"{start_year} vs {end_year} YTD"
            return TimeRange(start=start, end=end, label=label)

    # prefer the last occurrence to capture more specific context like "in 2023"
    year = int(matches[-1].group(1))
    start = date(year, 1, 1)
    end = date(year + 1, 1, 1)
    return TimeRange(start=start, end=end, label=str(year))


def extract_time_range(text: str, today: Optional[date] = None) -> Optional[TimeRange]:
    today = today or current_date()
    print(f"[TIME_UTILS DEBUG] extract_time_range() using today: {today}, query: '{text}'")
    month_range = parse_month(text)
    if month_range:
        print(f"[TIME_UTILS DEBUG] Matched month range: {month_range}")
        return month_range
    quarter_range = parse_quarter(text)
    if quarter_range:
        print(f"[TIME_UTILS DEBUG] Matched quarter range: {quarter_range}")
        return quarter_range
    relative_range = parse_relative_range(text, today=today)
    if relative_range:
        print(f"[TIME_UTILS DEBUG] Matched relative range: {relative_range}")
        return relative_range
    year_range = parse_year(text)
    print(f"[TIME_UTILS DEBUG] Matched year range: {year_range}")
    return year_range


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
