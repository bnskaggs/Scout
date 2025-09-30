import sys
import types

yaml_stub = types.ModuleType("yaml")
yaml_stub.safe_load = lambda stream: {}
sys.modules.setdefault("yaml", yaml_stub)

duckdb_stub = types.ModuleType("duckdb")
sys.modules.setdefault("duckdb", duckdb_stub)

from app.sql_builder import _build_filters
from app.resolver import SemanticDimension, SemanticModel


def _semantic_model() -> SemanticModel:
    return SemanticModel(
        table="test",
        date_grain="month",
        dimensions={
            "month": SemanticDimension(name="month", column="month"),
        },
        metrics={},
    )


def test_month_filter_collapsed_range_uses_equality():
    semantic = _semantic_model()
    filters = [
        {"field": "month", "op": "between", "value": ["2024-02-01", "2024-02-01"]},
    ]

    where_clause = _build_filters(filters, semantic, alias="base")

    assert where_clause == "WHERE base.month = DATE '2024-02-01'"
