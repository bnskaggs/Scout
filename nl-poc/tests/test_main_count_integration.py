from datetime import date
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys

import pytest

# Provide minimal stubs for optional dependencies used by app.main imports
if "yaml" not in sys.modules:
    yaml_stub = ModuleType("yaml")
    yaml_stub.safe_load = lambda stream: {}
    sys.modules["yaml"] = yaml_stub

if "duckdb" not in sys.modules:
    duckdb_stub = ModuleType("duckdb")
    duckdb_stub.connect = lambda path, **kwargs: None
    duckdb_stub.DuckDBPyConnection = object
    duckdb_stub.Error = Exception
    sys.modules["duckdb"] = duckdb_stub

if "fastapi" not in sys.modules:
    fastapi_stub = ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def add_middleware(self, *args, **kwargs):
            return None

        def on_event(self, event):
            def decorator(func):
                return func

            return decorator

        def get(self, path):
            def decorator(func):
                return func

            return decorator

        def post(self, path):
            def decorator(func):
                return func

            return decorator

    fastapi_stub.FastAPI = FastAPI
    fastapi_stub.HTTPException = HTTPException
    fastapi_stub.Header = lambda *args, **kwargs: None
    sys.modules["fastapi"] = fastapi_stub

    middleware_module = ModuleType("fastapi.middleware")
    cors_module = ModuleType("fastapi.middleware.cors")

    class CORSMiddleware:
        def __init__(self, *args, **kwargs):
            pass

    cors_module.CORSMiddleware = CORSMiddleware
    middleware_module.cors = cors_module
    sys.modules["fastapi.middleware"] = middleware_module
    sys.modules["fastapi.middleware.cors"] = cors_module

if "pydantic" not in sys.modules:
    pydantic_stub = ModuleType("pydantic")

    class BaseModel:  # pragma: no cover - simple stub
        def __init__(self, **data):
            for key, value in data.items():
                setattr(self, key, value)

    pydantic_stub.BaseModel = BaseModel
    sys.modules["pydantic"] = pydantic_stub

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.executor import QueryResult
from app.main import AskRequest, _state, ask
from app.planner import build_plan_rule_based
from app.resolver import PlanResolver, SemanticDimension, SemanticMetric, SemanticModel


class _PlanResolver(PlanResolver):
    def __init__(self, semantic, executor):
        super().__init__(semantic, executor)
        self.last_plan = None

    def resolve(self, plan):
        resolved = super().resolve(plan)
        self.last_plan = resolved
        return resolved


class _ResolverExecutorStub:
    def find_closest_value(self, dimension, value):
        return value

    def closest_matches(self, dimension, value, limit: int = 5):
        return []

    def parse_date(self, value: str) -> date:
        return date.fromisoformat(value)


class _QueryExecutorStub:
    def __init__(self, records):
        self._result = QueryResult(records=records, runtime_ms=7.5, rowcount=len(records))
        self.queries = []

    def query(self, sql):
        self.queries.append(sql)
        return self._result


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


@pytest.fixture(autouse=True)
def restore_state():
    original = _state.copy()
    try:
        yield
    finally:
        _state.clear()
        _state.update(original)


def test_hollywood_stabbings_count_flow(monkeypatch):
    monkeypatch.setattr("app.main.build_plan", lambda question, prefer_llm: build_plan_rule_based(question))
    monkeypatch.setattr("app.main.get_last_intent_engine", lambda: "rule_based")
    monkeypatch.setattr("app.main.guardrails.enforce", lambda sql, plan: None)
    monkeypatch.setattr("app.main.guardrails.check_rowcap_exceeded", lambda truncated: None)
    monkeypatch.setattr("app.main.viz.choose_chart", lambda plan, records: {"type": "table", "data": []})
    monkeypatch.setattr("app.main.viz.build_narrative", lambda plan, records: "Narrative")

    semantic = _semantic_model()
    resolver_executor = _ResolverExecutorStub()
    resolver = _PlanResolver(semantic, resolver_executor)
    query_executor = _QueryExecutorStub(records=[{"count": 5}])

    monkeypatch.setitem(_state, "resolver", resolver)
    monkeypatch.setitem(_state, "executor", query_executor)
    monkeypatch.setitem(_state, "semantic", semantic)
    monkeypatch.setitem(_state, "source_csv", "demo.csv")

    response = ask(
        AskRequest(question="How many stabbings happened in Hollywood in March 2023?")
    )

    assert response["rowcount"] == 1
    assert query_executor.queries, "Expected SQL execution"
    assert "COUNT(*) AS count" in query_executor.queries[0]

    resolved_plan = resolver.last_plan or {}
    month_filters = [f for f in resolved_plan.get("filters", []) if f.get("field") == "month"]
    assert month_filters
    month_filter = month_filters[0]
    assert month_filter.get("value") == ["2023-03-01", "2023-04-01"]
    assert resolved_plan.get("aggregate") == "count"
