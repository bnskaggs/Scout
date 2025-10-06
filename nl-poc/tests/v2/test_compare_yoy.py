"""Test YoY compare with v0.2 baseline."""
from datetime import date

from app.nql import compile_payload


def test_yoy_with_diff_pct():
    """YoY outputs current + same_period_last_year baseline with diff_pct."""
    payload = {
        "nql_version": "0.2",
        "intent": "compare",
        "dataset": "la_crime",
        "metrics": [{"name": "incidents", "agg": "count", "alias": "incidents"}],
        "time": {
            "grain": "month",
            "window": {"type": "single_month", "start": "2023-12-01"},
        },
        "compare": {
            "baseline": "same_period_last_year",
            "method": "diff_pct",
        },
        "group_by": [],
        "filters": [],
        "sort": [],
    }

    result = compile_payload(payload, today=date(2024, 1, 15))
    plan = result.plan

    assert plan["compare"]["baseline"] == "same_period_last_year"
    assert plan["compare"]["method"] == "diff_pct"


def test_yoy_with_grouping():
    """YoY with grouping by area."""
    payload = {
        "nql_version": "0.2",
        "intent": "compare",
        "dataset": "la_crime",
        "metrics": [{"name": "incidents", "agg": "count", "alias": "incidents"}],
        "time": {
            "grain": "month",
            "window": {"type": "single_month", "start": "2023-12-01"},
        },
        "compare": {
            "baseline": "same_period_last_year",
            "method": "diff_pct",
        },
        "group_by": ["area"],
        "filters": [],
        "sort": [],
    }

    result = compile_payload(payload)
    plan = result.plan

    assert "area" in plan["group_by"]
    assert plan["compare"]["baseline"] == "same_period_last_year"
