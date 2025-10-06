"""Test top-K within group using ROW_NUMBER()."""
from pathlib import Path

from app.nql import compile_payload
from app.sql_builder import build
from app.resolver import load_semantic_model

SEMANTIC_PATH = Path(__file__).parent.parent.parent / "config" / "semantic.yml"


def test_topk_within_area():
    """Top K crimes within each area."""
    payload = {
        "nql_version": "0.2",
        "intent": "rank",
        "dataset": "la_crime",
        "metrics": [{"name": "incidents", "agg": "count", "alias": "incidents"}],
        "time": {
            "grain": "month",
            "window": {"type": "single_month", "start": "2023-12-01"},
        },
        "group_by": ["area", "crime_type"],
        "top_k_within_group": {
            "k": 3,
            "by": "incidents",
        },
        "filters": [],
        "sort": [],
    }

    result = compile_payload(payload)
    plan = result.plan

    assert plan["top_k_within_group"]["k"] == 3
    assert plan["top_k_within_group"]["by"] == "incidents"

    # Verify SQL contains ROW_NUMBER window function
    semantic = load_semantic_model(SEMANTIC_PATH)
    sql = build(plan, semantic)
    assert "ROW_NUMBER()" in sql
    assert "PARTITION BY" in sql
    assert "rn <= 3" in sql


def test_topk_5_within_month():
    """Top 5 within each month."""
    payload = {
        "nql_version": "0.2",
        "intent": "rank",
        "dataset": "la_crime",
        "metrics": [{"name": "incidents", "agg": "count", "alias": "incidents"}],
        "time": {
            "grain": "month",
            "window": {"type": "relative_months", "n": 6},
        },
        "group_by": ["month", "area"],
        "top_k_within_group": {
            "k": 5,
            "by": "incidents",
        },
        "filters": [],
        "sort": [],
    }

    result = compile_payload(payload)
    plan = result.plan

    assert plan["top_k_within_group"]["k"] == 5
    assert "month" in plan["group_by"]
    assert "area" in plan["group_by"]
