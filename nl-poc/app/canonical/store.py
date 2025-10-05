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
    """Result row returned from a canonical search."""

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
        self._ensure_tables()

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
            CanonicalCandidate(
                candidate=m.candidate,
                score=m.score,
                canonical=existing.get(_normalise(m.candidate)),
            )
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
        now = datetime.now(timezone.utc)
        promoter = promoted_by or "admin"
        score_value = float(score) if score is not None else 1.0
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM canonical_map WHERE dim = ? AND lower(synonym) = lower(?)",
                [dim, synonym],
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE canonical_map
                    SET synonym = ?,
                        canonical = ?,
                        score = ?,
                        promoted_by = ?,
                        promoted_at = ?
                    WHERE id = ?
                    """,
                    [synonym, canonical, score_value, promoter, now, int(existing[0])],
                )
            else:
                conn.execute(
                    """
                    INSERT INTO canonical_map (dim, synonym, canonical, score, promoted_by, promoted_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [dim, synonym, canonical, score_value, promoter, now],
                )
            version = self._bump_version(conn)
        return version

    def get_version(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT v FROM canonical_meta WHERE k = 'version'"
            ).fetchone()
        return int(row[0]) if row else 1

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
                "SELECT dim, synonym, canonical, score FROM canonical_map"
            ).fetchall()
        mappings: Dict[str, Dict[str, Dict[str, float]]] = {}
        for dim, synonym, canonical, score in rows:
            dim_map = mappings.setdefault(dim, {})
            dim_map[_normalise(str(synonym))] = {
                "canonical": str(canonical),
                "score": float(score or 0.0),
            }
        return mappings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self._db_path))

    def _ensure_tables(self) -> None:
        with self._connect() as conn:
            conn.execute("CREATE SEQUENCE IF NOT EXISTS canonical_map_id_seq START 1")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS canonical_map (
                    id BIGINT DEFAULT nextval('canonical_map_id_seq'),
                    dim TEXT NOT NULL,
                    synonym TEXT NOT NULL,
                    canonical TEXT NOT NULL,
                    score DOUBLE DEFAULT 1.0,
                    promoted_by TEXT,
                    promoted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id)
                )
                """
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS canonical_map_dim_syn ON canonical_map(dim, synonym)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS canonical_meta (
                    k TEXT PRIMARY KEY,
                    v BIGINT NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT INTO canonical_meta(k, v) VALUES ('version', 1) ON CONFLICT (k) DO NOTHING"
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
        values: List[str] = []
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()
            values.extend(str(row[0]) for row in rows if row and row[0] is not None)
            synonym_rows = conn.execute(
                "SELECT synonym FROM canonical_map WHERE dim = ?",
                [dim],
            ).fetchall()
            canonical_rows = conn.execute(
                "SELECT canonical FROM canonical_map WHERE dim = ?",
                [dim],
            ).fetchall()
        values.extend(str(row[0]) for row in synonym_rows if row and row[0])
        values.extend(str(row[0]) for row in canonical_rows if row and row[0])
        # deduplicate while preserving order
        seen = set()
        deduped: List[str] = []
        for value in values:
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(value)
        return deduped

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
        return {_normalise(str(synonym)): str(canonical) for synonym, canonical in rows}

    def _bump_version(self, conn: duckdb.DuckDBPyConnection) -> int:
        current = conn.execute(
            "SELECT v FROM canonical_meta WHERE k = 'version'"
        ).fetchone()
        if current:
            next_value = int(current[0]) + 1
            conn.execute(
                "UPDATE canonical_meta SET v = ? WHERE k = 'version'",
                [next_value],
            )
            return next_value
        conn.execute("INSERT INTO canonical_meta(k, v) VALUES ('version', 1)")
        return 1


def _normalise(value: str) -> str:
    return value.strip().lower()
