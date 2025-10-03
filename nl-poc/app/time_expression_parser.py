"""Convert natural language time expressions into concrete date ranges."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Dict, Optional

from .time_utils import current_date


_LAST_WEEKS_PATTERN = re.compile(r"\blast\s+(?P<count>\d{1,2})\s+weeks?\b", re.IGNORECASE)
_QUARTER_PATTERN = re.compile(
    r"\b(?:q(?P<q1>[1-4])\s*(?P<year1>[12]\d{3})|(?P<year2>[12]\d{3})\s*[-\/]?\s*q(?P<q2>[1-4]))\b",
    re.IGNORECASE,
)
_MONTH_ONLY_PATTERN = re.compile(r"^\s*(?P<year>[12]\d{3})[-/](?P<month>0[1-9]|1[0-2])\s*$")
_YEAR_ONLY_PATTERN = re.compile(r"^\s*(?P<year>[12]\d{3})\s*$")
_SINCE_PATTERN = re.compile(r"\bsince\s+(?P<rest>.+)", re.IGNORECASE)


def _start_of_current_month(day: date) -> date:
    return day.replace(day=1)


def _start_of_previous_month(day: date) -> date:
    if day.month == 1:
        return date(day.year - 1, 12, 1)
    return date(day.year, day.month - 1, 1)


def _add_months(anchor: date, months: int) -> date:
    year = anchor.year + ((anchor.month - 1 + months) // 12)
    month = (anchor.month - 1 + months) % 12 + 1
    return date(year, month, 1)


def _format_chip_date(day: date) -> str:
    return day.strftime("%b %d").replace(" 0", " ")


def _parse_since_date(raw_text: str, today: date) -> date:
    cleaned = raw_text.strip()
    cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace(",", " ")
    formats_with_year = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%B %d %Y",
        "%b %d %Y",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%d %B %Y",
        "%d %b %Y",
    ]
    for fmt in formats_with_year:
        try:
            parsed = datetime.strptime(cleaned, fmt).date()
            return parsed
        except ValueError:
            continue

    formats_without_year = ["%B %d", "%b %d", "%m/%d", "%d %B", "%d %b"]
    for fmt in formats_without_year:
        try:
            parsed = datetime.strptime(cleaned, fmt)
            candidate = date(today.year, parsed.month, parsed.day)
            if candidate > today:
                candidate = date(today.year - 1, parsed.month, parsed.day)
            return candidate
        except ValueError:
            continue
    raise ValueError(f"Could not parse date from '{raw_text}'")


def _build_chip(expression: str, start: date, end: date, include_expression: bool) -> str:
    start_str = _format_chip_date(start)
    end_str = _format_chip_date(end)
    if include_expression:
        return f"{expression} = {start_str} → {end_str} (exclusive)"
    return f"{start_str} → {end_str} (exclusive)"


def parse_time_expression(expression: str, today: Optional[date] = None) -> Dict[str, str]:
    """Convert a natural language time expression into a concrete JSON-friendly range."""

    if not expression or not expression.strip():
        raise ValueError("expression must be a non-empty string")

    today = today or current_date()
    normalized = expression.strip()
    lowered = normalized.lower()

    # last month
    if re.search(r"\blast\s+month\b", lowered):
        start = _start_of_previous_month(today)
        end = _start_of_current_month(today)
        chips = _build_chip(normalized, start, end, include_expression=False)
        return {
            "expression": normalized,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "chips": chips,
        }

    # last N weeks
    match_weeks = _LAST_WEEKS_PATTERN.search(lowered)
    if match_weeks:
        count = int(match_weeks.group("count"))
        if count <= 0:
            raise ValueError("Number of weeks must be positive")
        end = today
        start = today - timedelta(weeks=count)
        chips = _build_chip(normalized, start, end, include_expression=False)
        return {
            "expression": normalized,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "chips": chips,
        }

    # since <date>
    match_since = _SINCE_PATTERN.search(lowered)
    if match_since:
        raw_date = expression[match_since.start("rest"):]
        start = _parse_since_date(raw_date, today)
        end = today
        chips = _build_chip(normalized, start, end, include_expression=False)
        return {
            "expression": normalized,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "chips": chips,
        }

    # Quarter like Q1 2024 or 2024 Q1
    match_quarter = _QUARTER_PATTERN.search(expression)
    if match_quarter:
        if match_quarter.group("q1") and match_quarter.group("year1"):
            quarter = int(match_quarter.group("q1"))
            year = int(match_quarter.group("year1"))
        else:
            quarter = int(match_quarter.group("q2"))
            year = int(match_quarter.group("year2"))
        start_month = (quarter - 1) * 3 + 1
        start = date(year, start_month, 1)
        end = _add_months(start, 3)
        chips = _build_chip(normalized, start, end, include_expression=True)
        return {
            "expression": normalized,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "chips": chips,
        }

    # Month like 2024-06
    match_month = _MONTH_ONLY_PATTERN.match(normalized)
    if match_month:
        year = int(match_month.group("year"))
        month = int(match_month.group("month"))
        start = date(year, month, 1)
        end = _add_months(start, 1)
        chips = _build_chip(normalized, start, end, include_expression=True)
        return {
            "expression": normalized,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "chips": chips,
        }

    # Year like 2023
    match_year = _YEAR_ONLY_PATTERN.match(normalized)
    if match_year:
        year = int(match_year.group("year"))
        start = date(year, 1, 1)
        end = date(year + 1, 1, 1)
        chips = _build_chip(normalized, start, end, include_expression=True)
        return {
            "expression": normalized,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "chips": chips,
        }

    raise ValueError(f"Unsupported time expression: '{expression}'")
