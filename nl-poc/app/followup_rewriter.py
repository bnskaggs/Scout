"""Lightweight follow-up query rewriter for the NQL pipeline.

The helper in this module implements a rule-based interpreter that merges a
fresh natural-language follow-up with the prior NQL state.  It deliberately
mirrors the simplified contract used by the TrueSight evaluation harness:

- The input is the last known state (`metric`, `time`, `group_by`, `filters`).
- The output is a new state plus an explicit ``action`` flag describing how
  the state changed: ``reset``, ``replace_dimension``, ``add_filter``, or
  ``reuse``.

The heuristics focus on the small collection of follow-up patterns described
in the spec.  They intentionally avoid depending on the broader NQL models so
the rewriter can run in isolation for unit tests.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional

Action = str


_METRIC_PATTERNS: Iterable[re.Pattern[str]] = (
    re.compile(
        r"\bhow many\s+([a-z][a-z0-9\s_-]*?)(?=\s+(?:happened|occurred|were|was|did|take|took|in|for|during|over|by|last|past|this|with|on|at)\b|[?.!])",
        re.I,
    ),
    re.compile(
        r"\bnumber of\s+([a-z][a-z0-9\s_-]*?)(?=\s+(?:in|for|during|over|by|last|past|this|with|on|at)\b|[?.!])",
        re.I,
    ),
    re.compile(
        r"\bcount of\s+([a-z][a-z0-9\s_-]*?)(?=\s+(?:in|for|during|over|by|last|past|this|with|on|at)\b|[?.!])",
        re.I,
    ),
    re.compile(
        r"\bshow(?:\s+me)?\s+([a-z][a-z0-9\s_-]*?)(?=\s+(?:in|for|during|over|by|last|past|this|with|on|at)\b|[?.!])",
        re.I,
    ),
    re.compile(
        r"\bgive me\s+([a-z][a-z0-9\s_-]*?)(?=\s+(?:in|for|during|over|by|last|past|this|with|on|at)\b|[?.!])",
        re.I,
    ),
)

_METRIC_STOPWORDS = {
    "happened",
    "occurred",
    "were",
    "was",
    "did",
    "take",
    "took",
    "are",
    "is",
    "be",
    "the",
    "a",
    "an",
    "of",
}

_TIME_PATTERNS: Iterable[tuple[re.Pattern[str], str]] = (
    (re.compile(r"\blast year\b", re.I), "last_year"),
    (re.compile(r"\bthis year\b", re.I), "this_year"),
    (re.compile(r"\blast month\b", re.I), "last_month"),
    (re.compile(r"\bthis month\b", re.I), "this_month"),
)

_TIME_RANGE_PATTERNS: Iterable[tuple[re.Pattern[str], str]] = (
    (
        re.compile(r"\blast\s+(\d{1,2})\s+(day|week|month|year)s?\b", re.I),
        "last_{n}_{unit}",
    ),
    (
        re.compile(r"\bpast\s+(\d{1,2})\s+(day|week|month|year)s?\b", re.I),
        "past_{n}_{unit}",
    ),
)

_YEAR_PATTERN = re.compile(r"\b(?:in|for|during)\s+(20\d{2})\b", re.I)
_BARE_YEAR_PATTERN = re.compile(r"\b20\d{2}\b")

_REPLACE_DIMENSION_PATTERN = re.compile(
    r"\b(?:same|instead)(?:\s+thing)?(?:\s+but)?\s+by\s+([a-z][a-z0-9\s_-]+)",
    re.I,
)
_GROUP_BY_PATTERN = re.compile(r"\bby\s+([a-z][a-z0-9\s_-]+)", re.I)

_FILTER_PATTERNS: Iterable[re.Pattern[str]] = (
    re.compile(r"\bonly\s+for\s+([\w\s'&/-]+)", re.I),
    re.compile(r"\bjust\s+([\w\s'&/-]+)", re.I),
    re.compile(r"\bfilter\s+to\s+([\w\s'&/-]+)", re.I),
    re.compile(r"\bin\s+([a-z][\w\s'&/-]+)", re.I),
)

_FILTER_STOPWORDS = {
    "please",
    "thanks",
    "thank",
    "now",
    "again",
}

_TIME_WORDS = {
    "last",
    "past",
    "this",
    "year",
    "month",
    "week",
    "day",
    "today",
    "yesterday",
    "quarter",
    "since",
    "before",
    "after",
}


def _clean_identifier(text: str) -> Optional[str]:
    cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    if not cleaned:
        return None
    return cleaned.replace(" ", "_")


def _normalise_group_by(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, (list, tuple)):
        for item in value:
            if item:
                return str(item)
    return None


def _extract_metric(utterance: str) -> Optional[str]:
    for pattern in _METRIC_PATTERNS:
        match = pattern.search(utterance)
        if not match:
            continue
        candidate = match.group(1).strip()
        if not candidate:
            continue
        words = candidate.split()
        while words and words[-1].lower() in _METRIC_STOPWORDS:
            words.pop()
        if not words:
            continue
        return " ".join(word.lower() for word in words)
    return None


def _extract_time(lowered: str) -> Optional[str]:
    for pattern, value in _TIME_PATTERNS:
        if pattern.search(lowered):
            return value

    for pattern, template in _TIME_RANGE_PATTERNS:
        match = pattern.search(lowered)
        if match:
            n = match.group(1)
            unit = match.group(2).lower()
            if not unit.endswith("s"):
                unit = f"{unit}s"
            return template.format(n=n, unit=unit)

    match = _YEAR_PATTERN.search(lowered)
    if match:
        return match.group(1)

    match = _BARE_YEAR_PATTERN.search(lowered)
    if match:
        return match.group(0)

    return None


def _extract_group_by(lowered: str) -> Optional[str]:
    match = _GROUP_BY_PATTERN.search(lowered)
    if not match:
        return None
    candidate = _clean_identifier(match.group(1))
    return candidate


def _extract_replace_dimension(lowered: str) -> Optional[str]:
    match = _REPLACE_DIMENSION_PATTERN.search(lowered)
    if not match:
        return None
    candidate = _clean_identifier(match.group(1))
    return candidate


def _clean_filter_value(raw: str) -> Optional[str]:
    value = raw.strip().strip(".,!? ")
    if not value:
        return None
    words = value.split()
    while words and words[-1].lower() in _FILTER_STOPWORDS:
        words.pop()
    if not words:
        return None
    candidate = " ".join(words)
    lowered = candidate.lower()
    if any(word in lowered.split() for word in _TIME_WORDS):
        return None
    if any(char.isdigit() for char in lowered):
        return None
    return candidate


def _extract_filters(
    utterance: str,
    *,
    field: str,
) -> List[str]:
    filters: List[str] = []
    lowered = utterance.lower()
    for pattern in _FILTER_PATTERNS:
        match = pattern.search(lowered)
        if not match:
            continue
        raw = utterance[match.start(1) : match.end(1)]
        value = _clean_filter_value(raw)
        if not value:
            continue
        formatted_value = value.title()
        filters.append(f"{field} = '{formatted_value}'")
    return filters


def _deduplicate(items: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _determine_filter_field(
    previous_group_by: Optional[str],
    candidate_group_by: Optional[str],
) -> str:
    if candidate_group_by:
        return candidate_group_by
    if previous_group_by:
        return previous_group_by
    return "area"


def rewrite_followup_state(
    last_state: Dict[str, object],
    utterance: str,
) -> Dict[str, object]:
    """Rewrite the follow-up utterance against the prior state.

    Parameters
    ----------
    last_state:
        The most recent simplified NQL state.
    utterance:
        The user's follow-up in natural language.
    """

    if not last_state:
        raise ValueError("last_state cannot be empty")

    lowered = utterance.lower()

    previous_metric = str(last_state.get("metric", "")) or None
    previous_time = str(last_state.get("time", "")) or None
    previous_group = _normalise_group_by(last_state.get("group_by"))
    previous_filters = list(last_state.get("filters", []))

    metric_candidate = _extract_metric(utterance)
    time_candidate = _extract_time(lowered)
    replace_dimension = _extract_replace_dimension(lowered)
    group_by_candidate = _extract_group_by(lowered)

    filter_field = _determine_filter_field(previous_group, group_by_candidate)
    filter_candidates = _extract_filters(utterance, field=filter_field)

    action: Action

    if metric_candidate and metric_candidate != (previous_metric or ""):
        action = "reset"
    elif metric_candidate and time_candidate:
        action = "reset"
    else:
        action = "reuse"

    if action == "reset":
        metric = metric_candidate or previous_metric or ""
        time_value = time_candidate or "all_time"
        group_by_value = replace_dimension or group_by_candidate
        filters = filter_candidates
        return {
            "action": action,
            "metric": metric,
            "time": time_value,
            "group_by": group_by_value,
            "filters": filters,
        }

    if replace_dimension:
        metric = metric_candidate or previous_metric or ""
        time_value = time_candidate or previous_time or "all_time"
        group_by_value = replace_dimension
        filters = previous_filters
        if filter_candidates:
            filters = _deduplicate([*filters, *filter_candidates])
        return {
            "action": "replace_dimension",
            "metric": metric,
            "time": time_value,
            "group_by": group_by_value,
            "filters": filters,
        }

    if filter_candidates:
        metric = metric_candidate or previous_metric or ""
        time_value = time_candidate or previous_time or "all_time"
        group_by_value = previous_group
        filters = _deduplicate([*previous_filters, *filter_candidates])
        return {
            "action": "add_filter",
            "metric": metric,
            "time": time_value,
            "group_by": group_by_value,
            "filters": filters,
        }

    metric = metric_candidate or previous_metric or ""
    time_value = time_candidate or previous_time or "all_time"
    group_by_value = group_by_candidate or previous_group
    return {
        "action": action,
        "metric": metric,
        "time": time_value,
        "group_by": group_by_value,
        "filters": previous_filters,
    }


__all__ = ["rewrite_followup_state"]

