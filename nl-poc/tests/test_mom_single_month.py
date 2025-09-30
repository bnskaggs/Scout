import sys
from datetime import date
from pathlib import Path
from types import ModuleType

if "yaml" not in sys.modules:
    yaml_stub = ModuleType("yaml")
    yaml_stub.safe_load = lambda stream: {}
    sys.modules["yaml"] = yaml_stub

if "duckdb" not in sys.modules:
    duckdb_stub = ModuleType("duckdb")
    duckdb_stub.connect = lambda path: None
    duckdb_stub.DuckDBPyConnection = object
    duckdb_stub.Error = Exception
    sys.modules["duckdb"] = duckdb_stub

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import sql_builder
from app.planner import build_plan
from app.resolver import PlanResolver, SemanticDimension, SemanticMetric, SemanticModel


class _ExecutorStub:
    def find_closest_value(self, dimension, value):
        return value

    def closest_matches(self, dimension, value, limit=5):  # pragma: no cover - defensive
        return []

    def parse_date(self, value):
        return date.fromisoformat(value)


def _semantic_model():
    return SemanticModel(
        table="la_crime_raw",
        date_grain="month",
        dimensions={
            "month": SemanticDimension(name="month", column="DATE OCC"),
        },
        metrics={
            "incidents": SemanticMetric(name="incidents", agg="count", grain=["month"]),
        },
    )


def test_single_month_mom_expands_internal_window():
    semantic = _semantic_model()
    resolver = PlanResolver(semantic, _ExecutorStub())

    plan = build_plan("Incidents in 2024-08; include MoM change.", prefer_llm=False)
    resolved = resolver.resolve(plan)

    internal_window = resolved.get("internal_window")
    assert internal_window == {
        "field": "month",
        "op": "between",
        "value": ["2024-07-01", "2024-09-01"],
    }

    sql = sql_builder.build(resolved, semantic)

    assert "prior_incidents" in sql
    assert "base.month >= DATE '2024-07-01' AND base.month < DATE '2024-09-01'" in sql
    assert "WHERE month = DATE '2024-08-01'" in sql


def test_multi_month_mom_keeps_original_window(monkeypatch):
    semantic = _semantic_model()
    resolver = PlanResolver(semantic, _ExecutorStub())

    monkeypatch.setattr("app.time_utils.current_date", lambda: date(2024, 9, 15))

    plan = build_plan("Incidents over the past 3 months; include MoM change.", prefer_llm=False)
    resolved = resolver.resolve(plan)

    assert "internal_window" not in resolved

    sql = sql_builder.build(resolved, semantic)

    assert "base.month >= DATE '2024-07-01' AND base.month < DATE '2024-10-01'" in sql
    assert "WHERE month = DATE" not in sql
    assert "2024-06-01" not in sql
    assert "2024-11-01" not in sql
