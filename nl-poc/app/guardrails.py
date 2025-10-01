"""Simple SQL guardrails for the prototype."""
from __future__ import annotations

import re
from typing import Dict, Optional


class GuardrailError(Exception):
    pass


_SELECT_ONLY = re.compile(r"^\s*(?:with\s+.*?\)?\s*)?select", re.IGNORECASE | re.DOTALL)
_SEMICOLON = re.compile(r";\s*")
_SELECT_STAR = re.compile(r"select\s+\*", re.IGNORECASE)


def enforce(sql: str, plan: Dict[str, object]) -> None:
    """
    Enforce SQL safety rules.
    Raises GuardrailError on violations.
    """
    if not _SELECT_ONLY.match(sql):
        raise GuardrailError("Only SELECT statements are permitted.")
    if _SEMICOLON.search(sql):
        raise GuardrailError("Multiple statements are not allowed.")
    if _SELECT_STAR.search(sql):
        raise GuardrailError("SELECT * is not permitted; select explicit columns instead.")
    limit = plan.get("limit", 0)
    if limit and limit > 2000:
        raise GuardrailError("LIMIT must be <= 2000.")


def check_rowcap_exceeded(truncated: bool) -> Optional[str]:
    """
    Return a friendly warning message if rowcap was hit, else None.
    """
    if not truncated:
        return None
    return (
        "Result set exceeds 10,000 rows and has been truncated. "
        "Please refine your filters or add a time range to narrow the results."
    )
