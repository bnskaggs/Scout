import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict

sys.path.append(str(Path(__file__).resolve().parents[1]))

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

    def Header(default=None, **_kwargs):  # pragma: no cover - simple stub
        return default

    class FastAPI:  # pragma: no cover - minimal test stub
        def __init__(self, *args, **kwargs):
            self._middlewares = []

        def add_middleware(self, *args, **kwargs):
            self._middlewares.append((args, kwargs))

        def on_event(self, _event: str):
            def decorator(func):
                return func

            return decorator

        def get(self, _path: str):
            def decorator(func):
                return func

            return decorator

        def post(self, _path: str):
            def decorator(func):
                return func

            return decorator

    fastapi_stub.FastAPI = FastAPI
    fastapi_stub.HTTPException = HTTPException
    fastapi_stub.Header = Header

    cors_module = ModuleType("fastapi.middleware.cors")

    class CORSMiddleware:  # pragma: no cover - minimal test stub
        def __init__(self, *args, **kwargs):
            pass

    cors_module.CORSMiddleware = CORSMiddleware
    middleware_module = ModuleType("fastapi.middleware")
    middleware_module.cors = cors_module

    fastapi_stub.middleware = middleware_module

    sys.modules["fastapi"] = fastapi_stub
    sys.modules["fastapi.middleware"] = middleware_module
    sys.modules["fastapi.middleware.cors"] = cors_module

if "pydantic" not in sys.modules:
    pydantic_stub = ModuleType("pydantic")

    class BaseModel:  # pragma: no cover - lightweight stand-in
        def __init__(self, **data):
            annotations = getattr(self.__class__, "__annotations__", {})
            for name, _ in annotations.items():
                if name in data:
                    setattr(self, name, data[name])
                else:
                    setattr(self, name, getattr(self.__class__, name, None))
            for extra_key, extra_value in data.items():
                if extra_key not in annotations:
                    setattr(self, extra_key, extra_value)

        def dict(self, *args, **kwargs):
            annotations = getattr(self.__class__, "__annotations__", {})
            return {name: getattr(self, name, None) for name in annotations}

        @classmethod
        def parse_obj(cls, data):
            if not isinstance(data, dict):
                raise TypeError("parse_obj expects a dict")
            return cls(**data)

        def copy(self, *args, **kwargs):  # pragma: no cover - minimal helper
            return self.__class__(**self.dict())

    def Field(default=None, default_factory=None, **_kwargs):  # pragma: no cover
        if default_factory is not None:
            return default_factory()
        return default

    class ValidationError(Exception):
        pass

    pydantic_stub.BaseModel = BaseModel
    pydantic_stub.Field = Field
    pydantic_stub.ValidationError = ValidationError
    sys.modules["pydantic"] = pydantic_stub

if "yaml" not in sys.modules:
    yaml_stub = ModuleType("yaml")
    yaml_stub.safe_load = lambda stream: {}
    sys.modules["yaml"] = yaml_stub

from app import main
from app.conversation import ConversationStore


def _fake_execute_query(plan: Dict[str, Any], utterance: str, *, intent_engine: str) -> Dict[str, Any]:
    return {
        "answer": "stub",
        "table": [],
        "chart": None,
        "sql": "SELECT 1",
        "plan": plan,
        "engine": intent_engine,
        "runtime_ms": 0,
        "rowcount": 0,
        "warnings": [],
        "lineage": {},
        "nql": plan.get("_nql"),
    }


def _stub_plan() -> Dict[str, Any]:
    return {
        "_nql": {
            "dimensions": [],
            "group_by": [],
            "filters": [],
            "time": {"window": {}},
        }
    }


def _reset_state(monkeypatch) -> None:
    monkeypatch.setattr(main, "_conversations", ConversationStore(), raising=False)
    monkeypatch.setattr(main, "build_plan", lambda utterance, prefer_llm=True: _stub_plan())
    monkeypatch.setattr(main, "_execute_query", _fake_execute_query)
    monkeypatch.setattr(main, "get_last_nql_status", lambda: {"attempted": True, "valid": True})


def test_chat_complete_attempts_nql_when_enabled(monkeypatch):
    _reset_state(monkeypatch)
    monkeypatch.setenv("USE_NQL", "true")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")

    payload = main.ChatCompleteRequest(session_id="demo", utterance="Show incidents")
    response = main.chat_complete(payload, x_session_id="demo")

    assert response["nql_status"]["attempted"] is True


def test_chat_complete_gate_respects_flag(monkeypatch):
    _reset_state(monkeypatch)
    monkeypatch.setenv("USE_NQL", "false")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")

    payload = main.ChatCompleteRequest(session_id="demo", utterance="Show incidents")
    response = main.chat_complete(payload, x_session_id="demo")

    assert response["nql_status"]["attempted"] is False
    assert response["nql_status"]["reason"] == "use_nql_flag_false"
