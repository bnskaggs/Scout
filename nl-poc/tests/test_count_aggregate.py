import sys
from datetime import date
from pathlib import Path
from types import ModuleType

sys.path.append(str(Path(__file__).resolve().parents[1]))

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

from app.planner import build_plan_rule_based
from app.resolver import PlanResolver, SemanticModel, SemanticDimension, SemanticMetric
from app.sql_builder import build as build_sql


class _ExecutorStub:
    def find_closest_value(self, dimension, value):
        return value

    def closest_matches(self, dimension, value, limit: int = 5):  # pragma: no cover - not used
        return []

    def parse_date(self, value: str) -> date:
        return date.fromisoformat(value)


def _semantic_model() -> SemanticModel:
    return SemanticModel(
        table="la_crime_raw",
        date_grain="month",
        dimensions={
            "month": SemanticDimension(name="month", column="DATE OCC"),
            "area": SemanticDimension(name="area", column="AREA NAME"),
            "weapon": SemanticDimension(name="weapon", column="Weapon Desc"),
        },
        metrics={
            "incidents": SemanticMetric(name="incidents", agg="count", grain=["month"]),
        },
    )


def test_how_many_incidents_sets_count_aggregate():
    plan = build_plan_rule_based("How many incidents citywide?")
    assert plan.get("aggregate") == "count"
    assert plan.get("metrics") == ["incidents"]


def test_count_by_area_uses_count_metric():
    plan = build_plan_rule_based("count by area in 2024")
    assert plan.get("aggregate") == "count"
    assert plan.get("group_by") == ["area"]
    assert plan.get("metrics") == ["count"]

    resolver = PlanResolver(_semantic_model(), _ExecutorStub())
    resolved = resolver.resolve(plan)
    sql = build_sql(resolved, _semantic_model())
    assert "COUNT(*) AS count" in sql


def test_number_of_stabbings_adds_weapon_filter():
    plan = build_plan_rule_based("number of stabbings last month")
    assert plan.get("aggregate") == "count"
    filters = plan.get("filters") or []
    assert any(f.get("field") == "weapon" for f in filters)
