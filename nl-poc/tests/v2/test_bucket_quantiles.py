"""Test bucket with quantiles and custom edges."""
from pathlib import Path

from app.nql import compile_payload
from app.sql_builder import build
from app.resolver import load_semantic_model

SEMANTIC_PATH = Path(__file__).parent.parent.parent / "config" / "semantic.yml"


def test_quartiles_bucketing():
    """Bucket incidents into quartiles."""
    payload = {
        "nql_version": "0.2",
        "intent": "distribution",
        "dataset": "la_crime",
        "metrics": [{"name": "incidents", "agg": "count", "alias": "incidents"}],
        "time": {
            "grain": "month",
            "window": {"type": "single_month", "start": "2023-12-01"},
        },
        "bucket": {
            "field": "incidents",
            "method": "quantile",
            "params": {"q": [0, 0.25, 0.5, 0.75, 1]},
        },
        "filters": [],
        "sort": [],
    }

    result = compile_payload(payload)
    plan = result.plan

    assert plan["bucket"]["method"] == "quantile"
    assert plan["bucket"]["params"]["q"] == [0, 0.25, 0.5, 0.75, 1]

    # Verify SQL uses PERCENTILE_DISC
    semantic = load_semantic_model(SEMANTIC_PATH)
    sql = build(plan, semantic)
    assert "PERCENTILE_DISC" in sql


def test_deciles_bucketing():
    """Bucket into deciles."""
    payload = {
        "nql_version": "0.2",
        "intent": "distribution",
        "dataset": "la_crime",
        "metrics": [{"name": "incidents", "agg": "count", "alias": "incidents"}],
        "time": {
            "grain": "month",
            "window": {"type": "single_month", "start": "2023-12-01"},
        },
        "bucket": {
            "field": "incidents",
            "method": "quantile",
            "params": {"q": [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1]},
        },
        "filters": [],
        "sort": [],
    }

    result = compile_payload(payload)
    plan = result.plan

    assert len(plan["bucket"]["params"]["q"]) == 11


def test_custom_edges():
    """Bucket with custom edges."""
    payload = {
        "nql_version": "0.2",
        "intent": "distribution",
        "dataset": "la_crime",
        "metrics": [{"name": "incidents", "agg": "count", "alias": "incidents"}],
        "time": {
            "grain": "month",
            "window": {"type": "single_month", "start": "2023-12-01"},
        },
        "bucket": {
            "field": "incidents",
            "method": "custom",
            "params": {"edges": [0, 100, 500, 1000, 5000]},
        },
        "filters": [],
        "sort": [],
    }

    result = compile_payload(payload)
    plan = result.plan

    assert plan["bucket"]["method"] == "custom"
    assert plan["bucket"]["params"]["edges"] == [0, 100, 500, 1000, 5000]
