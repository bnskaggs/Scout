import sys
import types

yaml_stub = types.ModuleType("yaml")
yaml_stub.safe_load = lambda stream: {}
sys.modules.setdefault("yaml", yaml_stub)

duckdb_stub = types.ModuleType("duckdb")
sys.modules.setdefault("duckdb", duckdb_stub)

from app.sql_builder import _build_filters, build
from app.resolver import SemanticDimension, SemanticMetric, SemanticModel


def _semantic_model() -> SemanticModel:
    return SemanticModel(
        table="test",
        date_grain="month",
        dimensions={
            "month": SemanticDimension(name="month", column="month"),
            "area": SemanticDimension(name="area", column="area"),
        },
        metrics={
            "incidents": SemanticMetric(name="incidents", agg="count", grain=["month"]),
        },
    )


def test_month_filter_collapsed_range_uses_equality():
    semantic = _semantic_model()
    filters = [
        {"field": "month", "op": "between", "value": ["2024-02-01", "2024-02-01"]},
    ]

    where_clause = _build_filters(filters, semantic, alias="base")

    assert where_clause == "WHERE base.month = DATE '2024-02-01'"


def test_sql_builder_generates_count_without_grouping():
    semantic = _semantic_model()
    plan = {
        "metrics": ["incidents"],
        "group_by": [],
        "filters": [
            {
                "field": "month",
                "op": "between",
                "value": ["2023-03-01", "2023-04-01"],
                "exclusive_end": True,
            }
        ],
        "order_by": [],
        "limit": 0,
        "aggregate": "count",
        "extras": {},
    }

    sql = build(plan, semantic)

    assert "COUNT(*) AS count" in sql
    assert "GROUP BY" not in sql


def test_sql_builder_generates_grouped_counts():
    semantic = _semantic_model()
    plan = {
        "metrics": ["incidents"],
        "group_by": ["area"],
        "filters": [
            {
                "field": "month",
                "op": "between",
                "value": ["2023-03-01", "2023-04-01"],
                "exclusive_end": True,
            }
        ],
        "order_by": [],
        "limit": 0,
        "aggregate": "count",
        "extras": {},
    }

    sql = build(plan, semantic)

    assert "COUNT(*) AS count" in sql
    assert "GROUP BY base.\"area\"" in sql
