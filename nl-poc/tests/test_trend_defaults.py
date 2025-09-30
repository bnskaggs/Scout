import sys
from datetime import date
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.planner import build_plan


def _month_filters(plan):
    return [f for f in plan.get("filters", []) if f.get("field") == "month"]


def _months_between(start_iso: str, end_iso: str) -> int:
    start = date.fromisoformat(start_iso)
    end = date.fromisoformat(end_iso)
    return (end.year - start.year) * 12 + (end.month - start.month)


def test_trend_with_explicit_last_year(monkeypatch):
    monkeypatch.setattr("app.time_utils.current_date", lambda: date(2024, 5, 15))

    plan = build_plan(
        "Show trend of total incidents for the city over the last year",
        prefer_llm=False,
    )

    assert plan.get("group_by") == ["month"]
    assert plan.get("order_by") == [{"field": "month", "dir": "asc"}]

    month_filters = _month_filters(plan)
    assert len(month_filters) == 1
    month_filter = month_filters[0]
    assert month_filter.get("op") == "between"
    start, end = month_filter.get("value")
    assert _months_between(start, end) == 12


def test_trend_without_dates_defaults_to_last_year(monkeypatch):
    monkeypatch.setattr("app.time_utils.current_date", lambda: date(2024, 5, 15))

    plan = build_plan("Show trend of total incidents for the city", prefer_llm=False)

    assert plan.get("group_by") == ["month"]
    assert plan.get("order_by") == [{"field": "month", "dir": "asc"}]

    month_filters = _month_filters(plan)
    assert len(month_filters) == 1
    month_filter = month_filters[0]
    assert month_filter.get("op") == "between"
    start, end = month_filter.get("value")
    assert _months_between(start, end) == 12
