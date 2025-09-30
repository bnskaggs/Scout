import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


if "yaml" not in sys.modules:
    yaml_stub = ModuleType("yaml")
    yaml_stub.safe_load = lambda stream: {}
    sys.modules["yaml"] = yaml_stub

if "duckdb" not in sys.modules:
    duckdb_stub = ModuleType("duckdb")
    duckdb_stub.Error = Exception
    duckdb_stub.DuckDBPyConnection = object
    sys.modules["duckdb"] = duckdb_stub


sys.path.append(str(Path(__file__).resolve().parents[1]))


from app.resolver import PlanResolutionError, PlanResolver


class _PatternRejectingExecutor:
    def find_closest_value(self, dimension, value):  # pragma: no cover - should not be called
        raise AssertionError("pattern operators should not resolve values")

    def closest_matches(self, dimension, value, limit=5):  # pragma: no cover - not used
        return []

    def parse_date(self, value):  # pragma: no cover - not used
        return value


def _semantic_model():
    return SimpleNamespace(
        table="test",
        date_grain="month",
        dimensions={
            "weapon": SimpleNamespace(name="weapon", column="weapon", dtype="text"),
        },
        metrics={},
    )


def test_like_any_filter_preserves_wildcards():
    resolver = PlanResolver(_semantic_model(), _PatternRejectingExecutor())
    plan = {
        "metrics": [],
        "group_by": [],
        "filters": [
            {"field": "weapon", "op": "like_any", "value": ["%firearm%"]},
        ],
    }

    try:
        resolved_plan = resolver.resolve(plan)
    except PlanResolutionError as exc:  # pragma: no cover - explicit failure path
        pytest.fail(f"Plan resolution unexpectedly failed: {exc}")

    assert resolved_plan["filters"] == [
        {"field": "weapon", "op": "like_any", "value": ["%firearm%"]},
    ]
