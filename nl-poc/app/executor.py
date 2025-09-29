"""DuckDB execution utilities."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import duckdb


@dataclass
class QueryResult:
    records: List[Dict[str, object]]
    runtime_ms: float
    rowcount: int


class DuckDBExecutor:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn = duckdb.connect(str(db_path))
        self._conn.execute("PRAGMA threads=4")

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        return self._conn

    def parse_date(self, value: str) -> date:
        return datetime.fromisoformat(value).date()

    def query(self, sql: str) -> QueryResult:
        start = time.perf_counter()
        result = self._conn.execute(sql)
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
        records = [dict(zip(columns, row)) for row in rows]
        runtime_ms = (time.perf_counter() - start) * 1000
        return QueryResult(records=records, runtime_ms=runtime_ms, rowcount=len(records))

    def find_closest_value(self, dimension, value: str) -> Optional[str]:
        if not value:
            return None
        sql = f"SELECT DISTINCT {self._dimension_sql(dimension)} AS val FROM la_crime_raw"
        try:
            vals = [row[0] for row in self._conn.execute(sql).fetchall() if row[0] is not None]
        except duckdb.Error:
            return None
        norm = value.lower()
        for item in vals:
            if isinstance(item, str) and item.lower() == norm:
                return item
        # try startswith match
        for item in vals:
            if isinstance(item, str) and item.lower().startswith(norm):
                return item
        return None

    def closest_matches(self, dimension, value: str, limit: int = 5) -> List[str]:
        sql = f"SELECT DISTINCT {self._dimension_sql(dimension)} AS val FROM la_crime_raw"
        vals = [row[0] for row in self._conn.execute(sql).fetchall() if row[0] is not None]
        scored = []
        target = value.lower()
        for item in vals:
            if not isinstance(item, str):
                continue
            score = _levenshtein(target, item.lower())
            scored.append((score, item))
        scored.sort(key=lambda x: x[0])
        return [item for _, item in scored[:limit]]

    def _dimension_sql(self, dimension) -> str:
        column = dimension.column
        if dimension.name == "month":
            return "DATE_TRUNC('month', \"DATE OCC\")"
        return f'"{column}"' if " " in column else f'"{column}"'

    def close(self) -> None:
        self._conn.close()


def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (ca != cb)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]
