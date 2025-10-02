"""NQL parsing, validation, and compilation utilities."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Optional

from .model import NQLQuery
from .validator import NQLValidationError, validate_nql
from .compiler import compile_nql_query


@dataclass
class CompiledNQL:
    """Container for an NQL compilation result."""

    plan: Dict[str, Any]
    nql: NQLQuery


_USE_NQL_FLAG = os.getenv("USE_NQL", "true").lower() in {"1", "true", "yes", "on"}


def is_enabled() -> bool:
    """Return True if the NQL pipeline is enabled via environment flag."""

    return _USE_NQL_FLAG


def compile_payload(payload: Dict[str, Any], today: Optional[date] = None) -> CompiledNQL:
    """Validate and compile a raw payload dictionary into a planner plan."""

    try:
        nql = NQLQuery.parse_obj(payload)
    except Exception as exc:  # pragma: no cover - defensive guard around validation errors
        raise NQLValidationError(str(exc)) from exc

    validated = validate_nql(nql)
    plan = compile_nql_query(validated, today=today)
    return CompiledNQL(plan=plan, nql=validated)


__all__ = [
    "CompiledNQL",
    "NQLQuery",
    "NQLValidationError",
    "compile_payload",
    "is_enabled",
]
