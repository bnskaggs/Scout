"""Test MoM compare with v0.2 baseline and diff_abs/diff_pct."""
from datetime import date

from app.nql import compile_payload


def test_mom_single_month_with_diff_pct():
    """MoM on single month outputs current + baseline with diff_pct."""
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
            "baseline": "previous_period",
            "method": "diff_pct",
        },
        "group_by": [],
        "filters": [],
        "sort": [],
    }

    result = compile_payload(payload, today=date(2024, 1, 15))
    plan = result.plan

    assert plan["compare"]["baseline"] == "previous_period"
    assert plan["compare"]["method"] == "diff_pct"
    assert "_nql" in plan
    assert plan["_nql"]["nql_version"] == "0.2"


def test_mom_last_complete_month():
    """MoM on last complete month (relative_months)."""
    payload = {
        "nql_version": "0.2",
        "intent": "compare",
        "dataset": "la_crime",
        "metrics": [{"name": "incidents", "agg": "count", "alias": "incidents"}],
        "time": {
            "grain": "month",
            "window": {"type": "relative_months", "n": 1},
        },
        "compare": {
            "baseline": "previous_period",
            "method": "diff_pct",
        },
        "group_by": [],
        "filters": [],
        "sort": [],
    }

    result = compile_payload(payload, today=date(2024, 1, 15))
    plan = result.plan

    assert plan["compare"]["baseline"] == "previous_period"
    assert "single_month_required_for_mom" in plan["_critic_pass"]


def test_mom_diff_abs():
    """MoM with diff_abs method."""
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
            "baseline": "previous_period",
            "method": "diff_abs",
        },
        "group_by": [],
        "filters": [],
        "sort": [],
    }

    result = compile_payload(payload)
    plan = result.plan

    assert plan["compare"]["method"] == "diff_abs"
