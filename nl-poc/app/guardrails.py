"""Simple SQL guardrails for the prototype."""
from __future__ import annotations

import re
from typing import Dict


class GuardrailError(Exception):
    pass


_SELECT_ONLY = re.compile(r"^\s*(?:with\s+.*?\)?\s*)?select", re.IGNORECASE | re.DOTALL)
_SEMICOLON = re.compile(r";\s*")
_SELECT_STAR = re.compile(r"select\s+\*", re.IGNORECASE)


def enforce(sql: str, plan: Dict[str, object]) -> None:
    if not _SELECT_ONLY.match(sql):
        raise GuardrailError("Only SELECT statements are permitted.")
    if _SEMICOLON.search(sql):
        raise GuardrailError("Multiple statements are not allowed.")
    if _SELECT_STAR.search(sql):
        raise GuardrailError("SELECT * is not permitted; select explicit columns instead.")
    limit = plan.get("limit", 0)
    if limit and limit > 2000:
        raise GuardrailError("LIMIT must be <= 2000.")
