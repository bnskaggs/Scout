import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

if "duckdb" not in sys.modules:
    duckdb_stub = ModuleType("duckdb")
    duckdb_stub.connect = lambda path, **kwargs: None
    duckdb_stub.DuckDBPyConnection = object
    duckdb_stub.Error = Exception
    sys.modules["duckdb"] = duckdb_stub

if "fastapi" not in sys.modules:
    fastapi_stub = ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail):  # pragma: no cover - behaviour trivial
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def add_middleware(self, *args, **kwargs):  # pragma: no cover - behaviour trivial
            return None

        def on_event(self, event):  # pragma: no cover - behaviour trivial
            def decorator(func):
                return func

            return decorator

        def get(self, path):  # pragma: no cover - behaviour trivial
            def decorator(func):
                return func

            return decorator

        def post(self, path):  # pragma: no cover - behaviour trivial
            def decorator(func):
                return func

            return decorator

    fastapi_stub.FastAPI = FastAPI
    fastapi_stub.HTTPException = HTTPException
    fastapi_stub.Header = lambda *args, **kwargs: None
    sys.modules["fastapi"] = fastapi_stub

    middleware_module = ModuleType("fastapi.middleware")
    cors_module = ModuleType("fastapi.middleware.cors")

    class CORSMiddleware:  # pragma: no cover - behaviour trivial
        def __init__(self, *args, **kwargs):
            pass

    cors_module.CORSMiddleware = CORSMiddleware
    middleware_module.cors = cors_module
    sys.modules["fastapi.middleware"] = middleware_module
    sys.modules["fastapi.middleware.cors"] = cors_module

if "pydantic" not in sys.modules:
    pydantic_stub = ModuleType("pydantic")

    class BaseModel:  # pragma: no cover - behaviour trivial
        def __init__(self, **data):
            for key, value in data.items():
                setattr(self, key, value)

    pydantic_stub.BaseModel = BaseModel
    sys.modules["pydantic"] = pydantic_stub

if "yaml" not in sys.modules:
    yaml_stub = ModuleType("yaml")
    yaml_stub.safe_load = lambda stream: {}
    sys.modules["yaml"] = yaml_stub

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.executor import QueryResult
from app.main import AskRequest, _state, ask


class _ExecutorStub:
    def __init__(self, records, runtime_ms, rowcount):
        self._result = QueryResult(records=records, runtime_ms=runtime_ms, rowcount=rowcount)
        self.queries = []

    def query(self, sql):  # pragma: no cover - exercised in tests
        self.queries.append(sql)
        return self._result


class _ResolverStub:
    def resolve(self, plan):  # pragma: no cover - exercised in tests
        return {"metrics": ["incidents"], "filters": [], "time_window_label": "All time"}


class _MetricStub:
    def sql_expression(self):  # pragma: no cover - exercised in tests
        return "COUNT(*)"


@pytest.fixture(autouse=True)
def restore_state():
    original = _state.copy()
    try:
        yield
    finally:
        _state.clear()
        _state.update(original)


def test_ask_includes_execution_metadata(monkeypatch):
    monkeypatch.setattr("app.main.build_plan", lambda question, prefer_llm: {"question": question})
    monkeypatch.setattr("app.main.get_last_intent_engine", lambda: "heuristic")
    monkeypatch.setattr("app.main.guardrails.enforce", lambda sql, resolved_plan: None)
    monkeypatch.setattr("app.main.sql_builder.build", lambda resolved_plan, semantic: "SELECT 1")
    monkeypatch.setattr("app.main.viz.choose_chart", lambda resolved_plan, records: {"type": "bar", "data": []})
    monkeypatch.setattr("app.main.viz.build_narrative", lambda resolved_plan, records: "Narrative")

    executor = _ExecutorStub(records=[{"value": 1}], runtime_ms=12.5, rowcount=1)
    semantic = SimpleNamespace(metrics={"incidents": _MetricStub()})

    monkeypatch.setitem(_state, "executor", executor)
    monkeypatch.setitem(_state, "semantic", semantic)
    monkeypatch.setitem(_state, "resolver", _ResolverStub())
    monkeypatch.setitem(_state, "source_csv", "demo.csv")

    response = ask(AskRequest(question="How many incidents?"))

    assert response["engine"] == "heuristic"
    assert response["runtime_ms"] == pytest.approx(12.5)
    assert response["rowcount"] == 1
    assert response["lineage"]["runtime_ms"] == pytest.approx(12.5)
    assert "intent_engine" not in response
