"""NQL parsing, validation, and compilation utilities."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Optional

from ..llm_client import _load_env_once
from .model import NQLQuery
from .validator import NQLValidationError, validate_nql
from .compiler import compile_nql_query


@dataclass
class CompiledNQL:
    """Container for an NQL compilation result."""

    plan: Dict[str, Any]
    nql: NQLQuery


_TRUE_VALUES = {"1", "true", "yes", "on"}


def _coerce_env_flag(raw_value: Optional[str], *, default: bool = True) -> bool:
    if raw_value is None:
        return default
    return raw_value.strip().lower() in _TRUE_VALUES


def use_nql_enabled() -> bool:
    """Return True if the NQL pipeline is enabled via environment flag."""

    _load_env_once()
    raw = os.getenv("USE_NQL")
    return _coerce_env_flag(raw)


def is_enabled() -> bool:
    """Backwards-compatible wrapper for the legacy flag getter."""

    return use_nql_enabled()


def flag_state() -> Dict[str, Any]:
    """Return a snapshot of the USE_NQL flag raw value and computed state."""

    _load_env_once()
    raw = os.getenv("USE_NQL")
    return {"raw": raw, "enabled": _coerce_env_flag(raw)}


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
    "flag_state",
    "is_enabled",
    "use_nql_enabled",
]
