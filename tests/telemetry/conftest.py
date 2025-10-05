from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
NL_POC = ROOT / "nl-poc"
if str(NL_POC) not in sys.path:
    sys.path.append(str(NL_POC))


if "fastapi" not in sys.modules:
    fastapi_stub = ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: Any):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class APIRouter:
        def __init__(self, *args, **kwargs):
            self.routes: List[Tuple[str, str, Callable[..., Any]]] = []

        def post(self, path: str):
            def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
                self.routes.append(("POST", path, func))
                return func

            return decorator

    class FastAPI:
        def __init__(self, *args, **kwargs):
            self.routers: List[Any] = []

        def add_middleware(self, *args, **kwargs):  # pragma: no cover - stub behaviour
            return None

        def include_router(self, router):  # pragma: no cover - stub behaviour
            self.routers.append(router)
            return None

    fastapi_stub.APIRouter = APIRouter
    fastapi_stub.FastAPI = FastAPI
    fastapi_stub.HTTPException = HTTPException
    fastapi_stub.Header = lambda *args, **kwargs: None
    sys.modules["fastapi"] = fastapi_stub

    middleware_module = ModuleType("fastapi.middleware")
    cors_module = ModuleType("fastapi.middleware.cors")

    class CORSMiddleware:  # pragma: no cover - stub behaviour
        def __init__(self, *args, **kwargs):
            pass

    cors_module.CORSMiddleware = CORSMiddleware
    middleware_module.cors = cors_module
    sys.modules["fastapi.middleware"] = middleware_module
    sys.modules["fastapi.middleware.cors"] = cors_module

if "pydantic" not in sys.modules:
    pydantic_stub = ModuleType("pydantic")

    class BaseModelMeta(type):
        def __new__(mcls, name, bases, namespace):
            validators: List[Tuple[str, Callable[..., Any], bool]] = []
            for attr_name, attr_value in list(namespace.items()):
                config = getattr(attr_value, "__validator_config__", None)
                if config:
                    validators.append((config["field"], attr_value, config.get("pre", False)))
            namespace["__validators__"] = validators
            return super().__new__(mcls, name, bases, namespace)

    class BaseModel(metaclass=BaseModelMeta):
        def __init__(self, **data: Any):
            values: Dict[str, Any] = {}
            annotations = getattr(self.__class__, "__annotations__", {})
            for field in annotations:
                values[field] = data.get(field)
            for field, func, pre in self.__validators__:
                if pre:
                    values[field] = func(self.__class__, values.get(field))
            for field, func, pre in self.__validators__:
                if not pre:
                    values[field] = func(self.__class__, values.get(field))
            for field in annotations:
                setattr(self, field, values.get(field))

    def validator(field: str, *, pre: bool = False):
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            func.__validator_config__ = {"field": field, "pre": pre}
            return func

        return decorator

    pydantic_stub.BaseModel = BaseModel
    pydantic_stub.validator = validator
    sys.modules["pydantic"] = pydantic_stub
