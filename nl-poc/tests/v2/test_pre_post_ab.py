"""Test pre/post (absolute baseline) compare."""
from datetime import date

from app.nql import compile_payload, NQLValidationError
import pytest


def test_pre_post_with_explicit_bounds():
    """Pre/post supports explicit start/end bounds."""
    payload = {
        "nql_version": "0.2",
        "intent": "compare",
        "dataset": "la_crime",
        "metrics": [{"name": "incidents", "agg": "count", "alias": "incidents"}],
        "time": {
            "grain": "month",
            "window": {"type": "absolute", "start": "2023-06-01", "end": "2023-12-01"},
        },
        "compare": {
            "baseline": "absolute",
            "start": "2023-01-01",
            "end": "2023-06-01",
            "method": "diff_pct",
        },
        "group_by": [],
        "filters": [],
        "sort": [],
    }

    result = compile_payload(payload, today=date(2024, 1, 15))
    plan = result.plan

    assert plan["compare"]["baseline"] == "absolute"
    assert plan["compare"]["start"] == "2023-01-01"
    assert plan["compare"]["end"] == "2023-06-01"
    assert "baseline_absolute_requires_bounds" in plan["_critic_pass"]


def test_absolute_baseline_missing_bounds():
    """baseline='absolute' without start/end raises error."""
    payload = {
        "nql_version": "0.2",
        "intent": "compare",
        "dataset": "la_crime",
        "metrics": [{"name": "incidents", "agg": "count", "alias": "incidents"}],
        "time": {
            "grain": "month",
            "window": {"type": "absolute", "start": "2023-06-01", "end": "2023-12-01"},
        },
        "compare": {
            "baseline": "absolute",
            "method": "diff_pct",
            # Missing start/end
        },
        "group_by": [],
        "filters": [],
        "sort": [],
    }

    with pytest.raises(NQLValidationError, match="requires start and end"):
        compile_payload(payload)


def test_before_after_june_15():
    """Before/after June 15 comparison."""
    payload = {
        "nql_version": "0.2",
        "intent": "compare",
        "dataset": "la_crime",
        "metrics": [{"name": "incidents", "agg": "count", "alias": "incidents"}],
        "time": {
            "grain": "month",
            "window": {"type": "absolute", "start": "2023-06-15", "end": "2023-12-01"},
        },
        "compare": {
            "baseline": "absolute",
            "start": "2023-01-01",
            "end": "2023-06-15",
            "method": "diff_abs",
        },
        "group_by": [],
        "filters": [],
        "sort": [],
    }

    result = compile_payload(payload)
    plan = result.plan

    assert plan["compare"]["baseline"] == "absolute"
    assert plan["compare"]["method"] == "diff_abs"
