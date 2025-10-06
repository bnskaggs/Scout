"""Test median and distinct aggregates."""
from pathlib import Path

from app.nql import compile_payload
from app.sql_builder import build
from app.resolver import load_semantic_model

SEMANTIC_PATH = Path(__file__).parent.parent.parent / "config" / "semantic.yml"


def test_median_aggregate():
    """Median via PERCENTILE_DISC(0.5)."""
    payload = {
        "nql_version": "0.2",
        "intent": "aggregate",
        "dataset": "la_crime",
        "metrics": [{"name": "incidents", "agg": "count", "alias": "incidents"}],
        "time": {
            "grain": "month",
            "window": {"type": "single_month", "start": "2023-12-01"},
        },
        "group_by": ["area"],
        "aggregate_v2": {
            "median_of": "Vict Age",
            "estimator": "exact",
        },
        "filters": [],
        "sort": [],
    }

    result = compile_payload(payload)
    plan = result.plan

    assert plan["aggregate_v2"]["median_of"] == "Vict Age"
    assert plan["aggregate_v2"]["estimator"] == "exact"

    # Verify SQL uses PERCENTILE_DISC(0.5)
    semantic = load_semantic_model(SEMANTIC_PATH)
    sql = build(plan, semantic)
    assert "PERCENTILE_DISC(0.5)" in sql


def test_distinct_count():
    """Distinct count via COUNT(DISTINCT ...)."""
    payload = {
        "nql_version": "0.2",
        "intent": "aggregate",
        "dataset": "la_crime",
        "metrics": [{"name": "incidents", "agg": "count", "alias": "incidents"}],
        "time": {
            "grain": "month",
            "window": {"type": "single_month", "start": "2023-12-01"},
        },
        "group_by": ["area"],
        "aggregate_v2": {
            "distinct_of": "DR_NO",
            "estimator": "exact",
        },
        "filters": [],
        "sort": [],
    }

    result = compile_payload(payload)
    plan = result.plan

    assert plan["aggregate_v2"]["distinct_of"] == "DR_NO"

    # Verify SQL uses COUNT(DISTINCT ...)
    semantic = load_semantic_model(SEMANTIC_PATH)
    sql = build(plan, semantic)
    assert "COUNT(DISTINCT" in sql


def test_median_and_distinct_combined():
    """Both median and distinct in same query."""
    payload = {
        "nql_version": "0.2",
        "intent": "aggregate",
        "dataset": "la_crime",
        "metrics": [{"name": "incidents", "agg": "count", "alias": "incidents"}],
        "time": {
            "grain": "month",
            "window": {"type": "single_month", "start": "2023-12-01"},
        },
        "group_by": ["area"],
        "aggregate_v2": {
            "median_of": "Vict Age",
            "distinct_of": "DR_NO",
            "estimator": "exact",
        },
        "filters": [],
        "sort": [],
    }

    result = compile_payload(payload)
    plan = result.plan

    assert plan["aggregate_v2"]["median_of"] == "Vict Age"
    assert plan["aggregate_v2"]["distinct_of"] == "DR_NO"

    semantic = load_semantic_model(SEMANTIC_PATH)
    sql = build(plan, semantic)
    assert "PERCENTILE_DISC(0.5)" in sql
    assert "COUNT(DISTINCT" in sql


def test_approx_estimator():
    """Approx estimator for performance."""
    payload = {
        "nql_version": "0.2",
        "intent": "aggregate",
        "dataset": "la_crime",
        "metrics": [{"name": "incidents", "agg": "count", "alias": "incidents"}],
        "time": {
            "grain": "month",
            "window": {"type": "single_month", "start": "2023-12-01"},
        },
        "group_by": ["area"],
        "aggregate_v2": {
            "distinct_of": "DR_NO",
            "estimator": "approx",
        },
        "filters": [],
        "sort": [],
    }

    result = compile_payload(payload)
    plan = result.plan

    assert plan["aggregate_v2"]["estimator"] == "approx"
