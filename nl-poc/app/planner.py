"""Heuristic natural-language planner for the LA crime prototype."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from .synonyms import SynonymBundle, canonical_metric, detect_compare, find_dimension, load_synonyms
from .time_utils import TimeRange, extract_time_range


@dataclass
class Plan:
    metrics: List[str]
    group_by: List[str]
    filters: List[Dict[str, object]]
    order_by: List[Dict[str, str]]
    limit: int
    compare: Optional[Dict[str, object]] = None

    def to_dict(self) -> Dict[str, object]:
        data: Dict[str, object] = {
            "metrics": self.metrics,
            "group_by": self.group_by,
            "filters": self.filters,
            "order_by": self.order_by,
            "limit": self.limit,
        }
        if self.compare:
            data["compare"] = self.compare
        return data


_TOKEN_SPLIT = re.compile(r"[^A-Za-z0-9]+")
_TOP_N_PATTERN = re.compile(r"top\s+(\d+)", re.IGNORECASE)
_BOT_N_PATTERN = re.compile(r"bottom\s+(\d+)", re.IGNORECASE)
_LIMIT_PATTERN = re.compile(r"limit\s+(\d+)", re.IGNORECASE)
_IN_LIST_PATTERN = re.compile(r"([A-Za-z][A-Za-z\s]+?)\s+(?:vs\.?|versus)\s+([A-Za-z][A-Za-z\s]+)", re.IGNORECASE)


def _extract_tokens(text: str) -> List[str]:
    return [token for token in _TOKEN_SPLIT.split(text.lower()) if token]


def _detect_group_by(text: str, bundle: SynonymBundle) -> List[str]:
    text_lower = text.lower()
    group_by: List[str] = []
    for phrase, canonical in bundle.dimension_aliases.items():
        if canonical == "month":
            # month group-bys are usually explicitly asked via "trend" or "over time"
            continue
        if phrase in text_lower and canonical not in group_by:
            group_by.append(canonical)
    if "trend" in text_lower or "over time" in text_lower or "by month" in text_lower:
        group_by.append("month")
    # handle explicit "by <dimension>" patterns
    for match in re.finditer(r"by\s+([A-Za-z\s]+)", text_lower):
        keyword = match.group(1).strip()
        candidate = find_dimension(keyword, bundle)
        if candidate and candidate not in group_by:
            group_by.append(candidate)
    return group_by


def _detect_filters(text: str, bundle: SynonymBundle, time_range: Optional[TimeRange]) -> List[Dict[str, object]]:
    filters: List[Dict[str, object]] = []
    if time_range:
        filters.append(time_range.to_filter())
    # detect area/premise/crime_type filters via "for <value>" or "in <value>"
    text_lower = text.lower()
    for dim_key, canonical in bundle.dimension_aliases.items():
        if canonical in ("month",):
            continue
        pattern = re.compile(rf"(?:for|in|at|on)\s+({dim_key}[\w\s-]*)", re.IGNORECASE)
        for match in pattern.finditer(text):
            value = match.group(1)
            value = value.replace(dim_key, "", 1).strip().strip(",")
            if value:
                filters.append({"field": canonical, "op": "=", "value": value.title()})
    # fallback: capture "in Hollywood"-style fragments as area filters
    for match in re.finditer(r"(?:in|for|at)\s+([A-Za-z][A-Za-z\s]+)", text):
        candidate = match.group(1).strip().strip(",")
        if not candidate:
            continue
        if re.search(r"\b20\d{2}\b", candidate):
            continue
        if any(candidate.lower().startswith(prefix) for prefix in ("last", "this")):
            continue
        filters.append({"field": "area", "op": "=", "value": candidate.title()})
    # detect explicit quoted filters
    for quoted in re.findall(r'"([^\"]+)"', text):
        tokens = quoted.split()
        if len(tokens) >= 1:
            # assume area when unspecified
            filters.append({"field": "area", "op": "=", "value": quoted})
    # detect "X vs Y" pattern -> filter with IN list
    match = _IN_LIST_PATTERN.search(text)
    if match:
        candidates = [match.group(1).strip(), match.group(2).strip()]
        filters.append({"field": "area", "op": "in", "value": [c.title() for c in candidates]})
    return filters


def _detect_order(text: str) -> List[Dict[str, str]]:
    if _BOT_N_PATTERN.search(text):
        return [{"field": "incidents", "dir": "asc"}]
    # default to descending for top N or generic ranking requests
    if _TOP_N_PATTERN.search(text) or "top" in text.lower() or "highest" in text.lower():
        return [{"field": "incidents", "dir": "desc"}]
    if "lowest" in text.lower() or "bottom" in text.lower():
        return [{"field": "incidents", "dir": "asc"}]
    return []


def _detect_limit(text: str) -> int:
    for pattern in (_TOP_N_PATTERN, _BOT_N_PATTERN, _LIMIT_PATTERN):
        match = pattern.search(text)
        if match:
            return min(2000, max(1, int(match.group(1))))
    if "top" in text.lower():
        return 10
    return 50


def generate_plan(question: str) -> Dict[str, object]:
    bundle = load_synonyms()
    time_range = extract_time_range(question)
    metrics = ["incidents"]

    group_by = _detect_group_by(question, bundle)
    filters = _detect_filters(question, bundle, time_range)
    order_by = _detect_order(question)
    limit = _detect_limit(question)

    compare_keyword = detect_compare(question, bundle)
    compare = None
    if compare_keyword:
        compare = {"type": compare_keyword, "periods": 1}

    plan = Plan(
        metrics=metrics,
        group_by=group_by,
        filters=filters,
        order_by=order_by,
        limit=limit,
        compare=compare,
    )
    return plan.to_dict()
