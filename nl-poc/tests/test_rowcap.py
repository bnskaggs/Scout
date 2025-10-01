"""Test rowcap guardrail enforcement."""
import sys
from pathlib import Path
from types import ModuleType

if "yaml" not in sys.modules:
    yaml_stub = ModuleType("yaml")
    yaml_stub.safe_load = lambda stream: {}
    sys.modules["yaml"] = yaml_stub

if "duckdb" not in sys.modules:
    duckdb_stub = ModuleType("duckdb")
    duckdb_stub.Error = Exception
    duckdb_stub.DuckDBPyConnection = object
    duckdb_stub.connect = lambda path: None
    sys.modules["duckdb"] = duckdb_stub

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.guardrails import check_rowcap_exceeded


def test_no_truncation():
    """When truncated=False, no warning should be returned."""
    result = check_rowcap_exceeded(False)
    assert result is None


def test_truncation_returns_warning():
    """When truncated=True, a friendly warning message should be returned."""
    result = check_rowcap_exceeded(True)
    assert result is not None
    assert "10,000" in result or "10000" in result
    assert "refine" in result.lower() or "narrow" in result.lower()
