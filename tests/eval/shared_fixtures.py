"""Shared fixtures and helper utilities for the conversational eval suite."""
from __future__ import annotations

import json
import sys
import types
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

ROOT = Path(__file__).resolve().parents[2]
NL_POC = ROOT / "nl-poc"
if str(NL_POC) not in sys.path:  # pragma: no cover - import side effect
    sys.path.insert(0, str(NL_POC))

import pytest

# ---------------------------------------------------------------------------
# Minimal third-party stubs so the application modules can be imported safely
# inside the test environment without pulling heavy dependencies.
# ---------------------------------------------------------------------------

if "yaml" not in sys.modules:  # pragma: no cover - import side effect
    yaml_stub = types.ModuleType("yaml")

    def _safe_load(stream: Any) -> Dict[str, Any]:
        """Parse JSON-compatible YAML snippets.

        The semantic loader in the application only relies on PyYAML during
        normal execution.  For the tests we use deterministic fixtures instead,
        so we provide a lightweight replacement that understands JSON strings
        (a strict subset of YAML).  This keeps the test environment hermetic.
        """

        if hasattr(stream, "read"):
            text = stream.read()
        else:
            text = stream
        text = (text or "").strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # The eval suite only feeds JSON-compatible documents; fall back to
            # an empty mapping so optional consumers continue to operate.
            return {}

    yaml_stub.safe_load = _safe_load  # type: ignore[attr-defined]
    sys.modules["yaml"] = yaml_stub


if "duckdb" not in sys.modules:  # pragma: no cover - import side effect
    duckdb_stub = types.ModuleType("duckdb")

    @dataclass
    class _DummyConnection:
        """Placeholder connection used by resolver utilities."""

        def execute(self, *_args: Any, **_kwargs: Any) -> "_DummyConnection":
            raise RuntimeError("DuckDB is not available in the test environment")

        def close(self) -> None:
            return None

    def _connect(_path: Optional[str] = None, **_kwargs: Any) -> _DummyConnection:
        return _DummyConnection()

    duckdb_stub.connect = _connect  # type: ignore[attr-defined]
    duckdb_stub.DuckDBPyConnection = _DummyConnection  # type: ignore[attr-defined]
    duckdb_stub.Error = RuntimeError  # type: ignore[attr-defined]
    sys.modules["duckdb"] = duckdb_stub


# Import application modules after the lightweight stubs are registered.
from app.conversation import rewrite_followup
from app.nql import CompiledNQL, compile_payload
from app.resolver import (
    PlanResolutionError,
    PlanResolver,
    SemanticDimension,
    SemanticMetric,
    SemanticModel,
)
from app.sql_builder import build as build_sql


DEFAULT_TODAY = date(2024, 7, 15)
_BASE_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "nl-poc"
    / "tests"
    / "conversations"
    / "fixtures"
    / "fresh_hollywood_stabbings.json"
)


class DummyExecutor:
    """Lightweight executor that performs deterministic value resolution."""

    _VALUES: Dict[str, Iterable[str]] = {
        "area": {"Central", "Hollywood", "Mission", "77th Street", "Harbor"},
        "weapon": {"Firearm", "Knife", "Unknown"},
        "crime_type": {"Robbery", "Assault", "Burglary", "Homicide"},
        "premise": {"Street", "House", "Store"},
    }

    def find_closest_value(self, dimension: SemanticDimension, value: Any) -> Optional[str]:
        choices = self._VALUES.get(dimension.name, [])
        target = str(value).strip().lower()
        for candidate in choices:
            if candidate.lower() == target:
                return candidate
        return None

    def closest_matches(self, dimension: SemanticDimension, value: Any) -> Iterable[str]:
        return sorted(self._VALUES.get(dimension.name, []))[:3]

    def parse_date(self, raw: Any) -> date:
        return date.fromisoformat(str(raw))

    # The executor interface includes query execution hooks that are not needed
    # in the eval suite.  They intentionally raise to surface accidental usage.
    def execute(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover
        raise RuntimeError("Query execution is not supported in the eval suite")


def load_base_state() -> Dict[str, Any]:
    """Return the canonical baseline NQL state used to seed conversations."""

    payload = json.loads(_BASE_FIXTURE.read_text())
    return payload["initial_nql"]


def make_semantic_model() -> SemanticModel:
    """Construct the semantic model used by the resolver and SQL builder."""

    dimensions = {
        "month": SemanticDimension(name="month", column="DATE OCC"),
        "area": SemanticDimension(name="area", column="AREA NAME"),
        "weapon": SemanticDimension(name="weapon", column="Weapon Desc"),
        "crime_type": SemanticDimension(name="crime_type", column="Crm Cd Desc"),
        "premise": SemanticDimension(name="premise", column="Premis Desc"),
        "vict_age": SemanticDimension(name="vict_age", column="Vict Age", dtype="number"),
    }
    metrics = {
        "incidents": SemanticMetric(name="incidents", agg="count", grain=["month"]),
        "incident_count": SemanticMetric(name="incident_count", agg="count", grain=["month"]),
        "count": SemanticMetric(name="count", agg="count", grain=["month"]),
    }
    return SemanticModel(table="la_crime_raw", date_grain="month", dimensions=dimensions, metrics=metrics)


def build_eval_context() -> Dict[str, Any]:
    """Factory that mirrors the pytest fixtures for the CLI runner."""

    semantic = make_semantic_model()
    resolver = PlanResolver(semantic, DummyExecutor())

    def _compiler(payload: Dict[str, Any], *, today: date = DEFAULT_TODAY) -> CompiledNQL:
        return compile_payload(payload, today=today)

    def _sql_builder(plan: Dict[str, Any]) -> str:
        return build_sql(plan, semantic)

    return {
        "semantic_model": semantic,
        "resolver": resolver,
        "compiler": _compiler,
        "sql_builder": _sql_builder,
        "base_state": load_base_state(),
        "today": DEFAULT_TODAY,
    }


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def semantic_model() -> SemanticModel:
    return make_semantic_model()


@pytest.fixture(scope="session")
def base_state_template() -> Dict[str, Any]:
    return load_base_state()


@pytest.fixture
def base_state(base_state_template: Dict[str, Any]) -> Dict[str, Any]:
    return deepcopy(base_state_template)


@pytest.fixture(scope="session")
def resolver(semantic_model: SemanticModel) -> PlanResolver:
    return PlanResolver(semantic_model, DummyExecutor())


@pytest.fixture(scope="session")
def compiler() -> Callable[[Dict[str, Any], date], CompiledNQL]:
    def _compile(payload: Dict[str, Any], today: date) -> CompiledNQL:
        return compile_payload(payload, today=today)

    return _compile


@pytest.fixture(scope="session")
def sql_builder(semantic_model: SemanticModel) -> Callable[[Dict[str, Any]], str]:
    def _build(plan: Dict[str, Any]) -> str:
        return build_sql(plan, semantic_model)

    return _build


@pytest.fixture(scope="session")
def eval_today() -> date:
    return DEFAULT_TODAY


__all__ = [
    "DEFAULT_TODAY",
    "PlanResolutionError",
    "PlanResolver",
    "build_eval_context",
    "compiler",
    "load_base_state",
    "resolver",
    "rewrite_followup",
    "semantic_model",
    "sql_builder",
]
