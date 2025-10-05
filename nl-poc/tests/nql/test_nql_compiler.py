"""Golden tests for the NQL validator and compiler."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest

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

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.nql import NQLValidationError, compile_payload
from app.resolver import PlanResolver, SemanticDimension, SemanticMetric, SemanticModel


_FIXTURE_DIR = Path(__file__).parent / "fixtures"


class _ExecutorStub:
    def find_closest_value(self, dimension, value):
        return value

    def closest_matches(self, dimension, value, limit: int = 5):  # pragma: no cover - defensive
        return []

    def parse_date(self, value: str) -> date:
        return date.fromisoformat(value)


def _semantic_model() -> SemanticModel:
    return SemanticModel(
        table="la_crime_raw",
        date_grain="month",
        dimensions={
            "month": SemanticDimension(name="month", column="DATE OCC"),
            "weapon": SemanticDimension(name="weapon", column="Weapon Desc"),
        },
        metrics={
            "incidents": SemanticMetric(name="incidents", agg="count", grain=["month"]),
        },
    )


def _load_fixture(name: str) -> dict:
    path = _FIXTURE_DIR / name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def test_single_month_range_filter():
    payload = _load_fixture("single_month.json")
    compiled = compile_payload(payload)
    plan = compiled.plan
    assert plan["filters"] == [
        {
            "field": "month",
            "op": "between",
            "value": ["2023-06-01", "2023-07-01"],
        }
    ]
    assert plan["limit"] == 100
    assert plan["extras"]["rowcap_hint"] == 2000
    assert "single_month_equality" not in plan["_critic_pass"]
    compile_info = plan.get("compileInfo") or {}
    assert compile_info.get("metricAlias") == "incidents"
    assert compile_info.get("groupBy") == []


def test_quarter_window_enforces_exclusive_end():
    payload = _load_fixture("quarter.json")
    compiled = compile_payload(payload)
    plan = compiled.plan
    assert plan["filters"] == [
        {"field": "month", "op": "between", "value": ["2024-01-01", "2024-04-01"]}
    ]
    assert "quarter_exclusive_end" in plan["_critic_pass"]


def test_relative_months_window_bounds():
    payload = _load_fixture("relative_months.json")
    compiled = compile_payload(payload)
    plan = compiled.plan
    assert plan["filters"] == [
        {"field": "month", "op": "between", "value": ["2023-09-01", "2024-09-01"]}
    ]


def test_ytd_window_bounds():
    payload = _load_fixture("ytd.json")
    compiled = compile_payload(payload)
    plan = compiled.plan
    assert plan["filters"] == [
        {"field": "month", "op": "between", "value": ["2024-01-01", "2024-09-01"]}
    ]


def test_like_passthrough_preserves_pattern():
    payload = _load_fixture("like_passthrough.json")
    compiled = compile_payload(payload)
    plan = compiled.plan
    assert plan["filters"][0] == {
        "field": "weapon",
        "op": "like",
        "value": "%firearm%",
    }
    assert "like_passthrough" in plan["_critic_pass"]


def test_mom_single_month_expands_internal_window():
    payload = _load_fixture("mom_single_month.json")
    compiled = compile_payload(payload)
    resolver = PlanResolver(_semantic_model(), _ExecutorStub())
    resolved = resolver.resolve(compiled.plan)
    assert resolved["internal_window"] == {
        "field": "month",
        "op": "between",
        "value": ["2024-07-01", "2024-09-01"],
    }


def test_trend_defaults_group_by_and_sort():
    payload = _load_fixture("trend_default.json")
    compiled = compile_payload(payload)
    plan = compiled.plan
    assert plan["group_by"] == ["month"]
    assert plan["order_by"] == [{"field": "month", "dir": "asc"}]
    assert plan["filters"] == [
        {"field": "month", "op": "between", "value": ["2023-09-01", "2024-09-01"]}
    ]
    # validator should backfill the window span when omitted
    assert compiled.nql.time.window.n == 12


def test_invalid_sort_rejected():
    payload = _load_fixture("sort_invalid.json")
    with pytest.raises(NQLValidationError):
        compile_payload(payload)


def test_limit_clamp_enforced():
    payload = _load_fixture("limit_clamp.json")
    compiled = compile_payload(payload)
    plan = compiled.plan
    assert plan["limit"] == 2000
    assert plan["extras"]["rowcap_hint"] == 2000
    assert "limit_clamp" in plan["_critic_pass"]


def test_strict_json_rejects_unknown_fields():
    payload = _load_fixture("strict_json_invalid_field.json")
    with pytest.raises(NQLValidationError):
        compile_payload(payload)


def test_compile_preserves_aggregate_field():
    payload = _load_fixture("single_month.json")
    payload["aggregate"] = "count"
    compiled = compile_payload(payload)
    assert compiled.plan.get("aggregate") == "count"


def test_compile_compare_time_mode():
    payload = {
        "nql_version": "0.1",
        "intent": "compare",
        "dataset": "la_crime",
        "metrics": [
            {"name": "incidents", "agg": "count", "alias": "incidents"}
        ],
        "aggregate": "count",
        "dimensions": [],
        "filters": [],
        "time": {
            "grain": "month",
            "window": {
                "type": "absolute",
                "start": "2023-01-01",
                "end": "2025-01-01"
            },
        },
        "group_by": [],
        "sort": [],
        "limit": 100,
        "compare": {
            "mode": "time",
            "lhs_time": "2023-01-01/2024-01-01",
            "rhs_time": "2024-01-01/2025-01-01",
        },
    }
    compiled = compile_payload(payload)
    compare = compiled.plan.get("compare")
    assert compare is not None
    assert compare.get("mode") == "time"
    assert compare.get("lhs_time") == "2023-01-01/2024-01-01"
    assert compare.get("rhs_time") == "2024-01-01/2025-01-01"


def test_compile_compare_dimension_mode():
    payload = {
        "nql_version": "0.1",
        "intent": "compare",
        "dataset": "la_crime",
        "metrics": [
            {"name": "incidents", "agg": "count", "alias": "incidents"}
        ],
        "dimensions": [],
        "filters": [],
        "time": {
            "grain": "month",
            "window": {
                "type": "absolute",
                "start": "2024-01-01",
                "end": "2025-01-01"
            },
        },
        "group_by": [],
        "sort": [],
        "limit": 100,
        "compare": {
            "mode": "dimension",
            "dimension": "area",
        },
    }
    compiled = compile_payload(payload)
    compare = compiled.plan.get("compare")
    assert compare is not None
    assert compare.get("mode") == "dimension"
    assert compare.get("dimension") == "area"
