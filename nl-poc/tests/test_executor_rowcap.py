"""Simple integration test for executor rowcap behavior."""
import sys
from pathlib import Path
from types import ModuleType

if "yaml" not in sys.modules:
    yaml_stub = ModuleType("yaml")
    yaml_stub.safe_load = lambda stream: {}
    sys.modules["yaml"] = yaml_stub

if "duckdb" not in sys.modules:
    # Create mock DuckDB module
    duckdb_stub = ModuleType("duckdb")
    duckdb_stub.Error = Exception
    duckdb_stub.DuckDBPyConnection = object

    class MockResult:
        def __init__(self, num_rows):
            self.description = [("id",), ("value",)]
            self.num_rows = num_rows
            self._fetched = False

        def fetchall(self):
            if self._fetched:
                return []
            self._fetched = True
            return [(i, f"val_{i}") for i in range(self.num_rows)]

    class MockConnection:
        def __init__(self, num_rows=100):
            self.num_rows = num_rows

        def execute(self, sql):
            return MockResult(self.num_rows)

    duckdb_stub.connect = lambda path, **kwargs: MockConnection()
    sys.modules["duckdb"] = duckdb_stub

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.executor import DuckDBExecutor


def test_rowcap_under_limit():
    """When result is under 10k rows, truncated should be False."""
    # Mock a small result set
    sys.modules["duckdb"].connect = lambda path: sys.modules["duckdb"].MockConnection(num_rows=100)
    executor = DuckDBExecutor(Path("dummy.db"))

    result = executor.query("SELECT * FROM test", max_rows=10_000)

    assert result.rowcount == 100
    assert result.truncated is False
    print("✓ test_rowcap_under_limit passed")


def test_rowcap_over_limit():
    """When result exceeds 10k rows, truncated should be True."""
    # Mock a large result set (15k rows)
    sys.modules["duckdb"].connect = lambda path: sys.modules["duckdb"].MockConnection(num_rows=15_000)
    executor = DuckDBExecutor(Path("dummy.db"))

    result = executor.query("SELECT * FROM test", max_rows=10_000)

    assert result.rowcount == 10_000  # Capped at limit
    assert result.truncated is True
    print("✓ test_rowcap_over_limit passed")


if __name__ == "__main__":
    test_rowcap_under_limit()
    test_rowcap_over_limit()
    print("\nAll executor rowcap tests passed!")
