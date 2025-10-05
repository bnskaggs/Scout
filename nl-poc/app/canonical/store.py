"""Persistent storage helpers for canonical mappings."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import duckdb

from ..executor import DuckDBExecutor
from ..resolver import SemanticDimension, SemanticModel
from .fuzzy import FuzzyMatcher, FuzzyMatch


@dataclass
class CanonicalCandidate:
    candidate: str
    score: float
    canonical: Optional[str]


class CanonicalStore:
    """Manage canonical mappings stored in DuckDB."""

    def __init__(
        self,
        executor: DuckDBExecutor,
        semantic: SemanticModel,
        *,
        matcher: Optional[FuzzyMatcher] = None,
        max_candidates: int = 500,
    ) -> None:
        self._db_path = Path(executor.db_path)
        self._semantic = semantic
        self._matcher = matcher or FuzzyMatcher()
        self._max_candidates = max_candidates
        self._ensure_table()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def search(self, dim: str, token: str) -> List[CanonicalCandidate]:
        if not token:
            return []
        values = self._load_candidates(dim)
        matches: List[FuzzyMatch] = self._matcher.rank(token, values)
        existing = self._lookup_mapping(dim)
        return [
            CanonicalCandidate(candidate=m.candidate, score=m.score, canonical=existing.get(_normalise(m.candidate)))
            for m in matches
        ]

    def promote(
        self,
        dim: str,
        synonym: str,
        canonical: str,
        score: Optional[float],
        *,
        promoted_by: Optional[str] = None,
    ) -> int:
        next_version = self._next_version()
        now = datetime.now(timezone.utc)
        score_value = float(score) if score is not None else None
        promoter = promoted_by or "admin"
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM canonical_map WHERE dim = ? AND lower(synonym) = lower(?)",
                [dim, synonym],
            )
            conn.execute(
                """
                INSERT INTO canonical_map
                (dim, synonym, canonical, score, promoted_by, promoted_at, version)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [dim, synonym, canonical, score_value, promoter, now, next_version],
            )
        return next_version

    def get_version(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM canonical_map").fetchone()
        return int(row[0]) if row else 0

    def dimensions(self) -> List[str]:
        return list(self._semantic.dimensions.keys())

    def current_mapping(self, dim: str, synonym: str) -> Optional[str]:
        if not synonym:
            return None
        mapping = self._lookup_mapping(dim)
        return mapping.get(_normalise(synonym))

    def load_mappings(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT dim, synonym, canonical, score FROM canonical_map ORDER BY version"
            ).fetchall()
        mappings: Dict[str, Dict[str, Dict[str, float]]] = {}
        for dim, synonym, canonical, score in rows:
            dim_map = mappings.setdefault(dim, {})
            dim_map[_normalise(str(synonym))] = {"canonical": str(canonical), "score": float(score or 0.0)}
        return mappings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self._db_path))

    def _ensure_table(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS canonical_map (
                    dim TEXT NOT NULL,
                    synonym TEXT NOT NULL,
                    canonical TEXT NOT NULL,
                    score DOUBLE,
                    promoted_by TEXT,
                    promoted_at TIMESTAMP,
                    version BIGINT NOT NULL
                )
                """
            )

    def _load_candidates(self, dim: str) -> List[str]:
        dimension = self._dimension(dim)
        table = self._semantic.table
        column_sql = self._dimension_sql(dimension)
        sql = (
            f"SELECT DISTINCT {column_sql} AS value "
            f"FROM {table} "
            f"WHERE {column_sql} IS NOT NULL "
            f"LIMIT {self._max_candidates}"
        )
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [str(row[0]) for row in rows if row and row[0] is not None]

    def _dimension(self, dim: str) -> SemanticDimension:
        try:
            return self._semantic.dimensions[dim]
        except KeyError as exc:  # pragma: no cover - guard clause
            raise ValueError(f"Unknown dimension '{dim}'") from exc

    def _dimension_sql(self, dimension: SemanticDimension) -> str:
        column = dimension.column
        if dimension.name == "month":
            return "DATE_TRUNC('month', \"DATE OCC\")"
        if " " in column:
            return f'"{column}"'
        return f'"{column}"'

    def _lookup_mapping(self, dim: str) -> Dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT synonym, canonical FROM canonical_map WHERE dim = ?",
                [dim],
            ).fetchall()
        return { _normalise(str(synonym)): str(canonical) for synonym, canonical in rows }

    def _next_version(self) -> int:
        current = self.get_version()
        return current + 1


def _normalise(value: str) -> str:
    return value.strip().lower()
