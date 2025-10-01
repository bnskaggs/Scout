"""Smoke test to verify rowcap code changes compile and have correct signatures."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

# Test 1: Verify QueryResult has truncated field
from app.executor import QueryResult

result = QueryResult(records=[], runtime_ms=100.0, rowcount=5, truncated=False)
assert hasattr(result, "truncated"), "QueryResult missing 'truncated' field"
assert result.truncated is False, "Default truncated should be False"
print("[PASS] QueryResult.truncated field present")

result_truncated = QueryResult(records=[], runtime_ms=100.0, rowcount=10000, truncated=True)
assert result_truncated.truncated is True, "Truncated flag should be settable"
print("[PASS] QueryResult.truncated can be set to True")

# Test 2: Verify check_rowcap_exceeded function exists and works
from app.guardrails import check_rowcap_exceeded

warning_none = check_rowcap_exceeded(False)
assert warning_none is None, "Should return None when not truncated"
print("[PASS] check_rowcap_exceeded(False) returns None")

warning_msg = check_rowcap_exceeded(True)
assert warning_msg is not None, "Should return message when truncated"
assert isinstance(warning_msg, str), "Warning should be a string"
assert "10" in warning_msg, "Warning should mention row limit"
print("[PASS] check_rowcap_exceeded(True) returns: '{}'".format(warning_msg[:60]))

# Test 3: Verify DuckDBExecutor.query has max_rows parameter
from app.executor import DuckDBExecutor
import inspect

sig = inspect.signature(DuckDBExecutor.query)
params = list(sig.parameters.keys())
assert "max_rows" in params, "query() should have max_rows parameter"
assert sig.parameters["max_rows"].default == 10_000, "max_rows default should be 10_000"
print("[PASS] DuckDBExecutor.query() has max_rows=10_000 parameter")

print("\n[SUCCESS] All smoke tests passed! Rowcap implementation is structurally correct.")
print("\nManual verification needed:")
print("  1. Start the backend server: uvicorn app.main:app --reload")
print("  2. Open frontend/index.html in browser")
print("  3. Submit a broad query (e.g., 'Show all incidents')")
print("  4. Verify warning appears if result set is large")
