from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

# Ensure the application package is importable when running tests from the repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "nl-poc"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

# Provide a lightweight ``duckdb`` stub so importing ``app.main`` does not require the
# native dependency in the test environment.
if "duckdb" not in sys.modules:
    duckdb_stub = types.ModuleType("duckdb")
    duckdb_stub.DuckDBPyConnection = object  # type: ignore[attr-defined]
    sys.modules["duckdb"] = duckdb_stub

from app.main import app  # noqa: E402  (import after sys.path mutation)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Provide a FastAPI test client for the application."""

    # Disable heavy startup hooks that expect DuckDB files on disk.  The tests
    # exercise the AgentKit route in isolation with mocked dependencies.
    if hasattr(app.router, "on_startup"):
        app.router.on_startup.clear()  # type: ignore[attr-defined]
    if hasattr(app.router, "on_shutdown"):
        app.router.on_shutdown.clear()  # type: ignore[attr-defined]

    with TestClient(app) as test_client:
        yield test_client
