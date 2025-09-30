"""Hybrid intent planner with LLM primary path and rule-based fallback."""
from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from .llm_client import LLMNotConfigured, call_intent_llm, fill_time_tokens
from .synonyms import (
    SHARE_TOKENS,
    SynonymBundle,
    detect_compare,
    detect_weapon_patterns,
    find_dimension,
    load_synonyms,
    weapon_patterns_from_value,
)
from .time_utils import TimeRange, extract_time_range, trailing_year_range

PROMPT_PATH = pathlib.Path(__file__).parent / "llm_prompt_intent.txt"
SEMANTIC_PATH = pathlib.Path(__file__).parents[1] / "config" / "semantic.yml"

_LAST_ENGINE = "rule_based"


def get_last_intent_engine() -> str:
    """Return the planner engine used for the most recent plan."""

    return _LAST_ENGINE


def list_columns_for_prompt() -> List[str]:
    """Enumerate available columns for the prompt payload."""

    return [
        '"DATE OCC"',
        '"AREA NAME"',
        '"Crm Cd Desc"',
        '"Premis Desc"',
        '"Weapon Desc"',
        '"Vict Age"',
        '"DR_NO"',
    ]


@dataclass
class Plan:
    metrics: List[str]
    group_by: List[str]
    filters: List[Dict[str, object]]
    order_by: List[Dict[str, str]]
    limit: int
    compare: Optional[Dict[str, object]] = None
    extras: Optional[Dict[str, object]] = None

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
        if self.extras:
            data["extras"] = self.extras
        return data


_TOKEN_SPLIT = re.compile(r"[^A-Za-z0-9]+")
_TOP_N_PATTERN = re.compile(r"top\s+(\d+)", re.IGNORECASE)
_BOT_N_PATTERN = re.compile(r"bottom\s+(\d+)", re.IGNORECASE)
_LIMIT_PATTERN = re.compile(r"limit\s+(\d+)", re.IGNORECASE)
_IN_LIST_PATTERN = re.compile(r"\b([\w .&/-]+)\s+vs\.?\s+([\w .&/-]+)\b", re.IGNORECASE)


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
    if _IN_LIST_PATTERN.search(text):
        if "area" not in group_by:
            group_by.append("area")
    if ("weapon categories" in text_lower or "weapon category" in text_lower) and "weapon" not in group_by:
        group_by.append("weapon")
    if "area" in group_by and "across all areas" in text_lower:
        group_by = [dim for dim in group_by if dim != "area"]
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
        pattern = re.compile(rf"\b(?:for|in|at|on)\s+({dim_key}[\w\s-]*)", re.IGNORECASE)
        for match in pattern.finditer(text):
            value = match.group(1)
            value = value.replace(dim_key, "", 1).strip().strip(",")
            if value:
                filters.append({"field": canonical, "op": "=", "value": value.title()})
    # fallback: capture "in Hollywood"-style fragments as area filters
    for match in re.finditer(r"\b(?:in|for|at)\s+([A-Za-z][A-Za-z\s]+)", text):
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
    weapon_patterns = detect_weapon_patterns(text)
    if weapon_patterns and not any(f.get("field") == "weapon" for f in filters):
        filters.append({"field": "weapon", "op": "like_any", "value": weapon_patterns})
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
    return 0


def _has_rank_intent(text: str) -> bool:
    text_lower = text.lower()
    return bool(
        _TOP_N_PATTERN.search(text)
        or _BOT_N_PATTERN.search(text)
        or "top" in text_lower
        or "highest" in text_lower
        or "lowest" in text_lower
        or "rank" in text_lower
    )


def _question_specifies_grouping(
    question: str, bundle: SynonymBundle, group_by: List[str]
) -> bool:
    text_lower = question.lower()
    for phrase in bundle.dimension_aliases:
        if phrase == "month":
            continue
        normalized = phrase.lower()
        if f"by {normalized}" in text_lower:
            return True
    for dimension in group_by:
        if dimension == "month":
            continue
        canonical = dimension.replace("_", " ")
        if canonical and canonical in text_lower:
            return True
        if canonical and f"{canonical}s" in text_lower:
            return True
        for phrase, mapped in bundle.dimension_aliases.items():
            if mapped != dimension:
                continue
            normalized = phrase.lower()
            if normalized in text_lower or f"{normalized}s" in text_lower:
                return True
    return False


def _normalize_filters(
    question: str, filters: List[Dict[str, object]]
) -> List[Dict[str, object]]:
    normalized: List[Dict[str, object]] = []
    weapon_patterns = detect_weapon_patterns(question)
    for filt in filters or []:
        if not isinstance(filt, dict):
            continue
        current = dict(filt)
        field = current.get("field")
        if field == "month":
            op = current.get("op", "between")
            value = current.get("value")
            if isinstance(value, list):
                start = value[0] if value else None
                end = value[1] if len(value) > 1 else None
                if op == "between" and start and (not end or end == start):
                    current["op"] = "="
                    current["value"] = start
                elif op != "=" and len(value) == 1 and start:
                    current["op"] = "="
                    current["value"] = start
            elif op == "between" and isinstance(value, str):
                current["op"] = "="
        elif field == "weapon":
            value = current.get("value")
            collected: List[str] = []
            if isinstance(value, str):
                patterns = weapon_patterns_from_value(value)
                if patterns:
                    collected.extend(patterns)
            elif isinstance(value, list):
                for entry in value:
                    if isinstance(entry, str):
                        patterns = weapon_patterns_from_value(entry)
                        if patterns:
                            collected.extend(patterns)
            if collected:
                deduped = sorted(set(pattern.lower() for pattern in collected))
                current["op"] = "like_any"
                current["value"] = deduped
            elif current.get("op") == "like_any" and isinstance(value, list):
                current["value"] = [str(v).lower() for v in value]
        normalized.append(current)
    if weapon_patterns and not any(f.get("field") == "weapon" for f in normalized):
        normalized.append({"field": "weapon", "op": "like_any", "value": weapon_patterns})
    return normalized


def _post_process_plan(
    question: str, plan: Dict[str, object], bundle: SynonymBundle
) -> Dict[str, object]:
    text_lower = question.lower()
    group_by = plan.get("group_by") or []
    if not isinstance(group_by, list):
        group_by = [group_by]
    top_intent = _has_rank_intent(question)
    trend_tokens = ("trend" in text_lower) or ("by month" in text_lower) or ("monthly" in text_lower)
    if trend_tokens:
        group_by = ["month"]
    compare = plan.get("compare")
    if compare and not _question_specifies_grouping(question, bundle, group_by):
        group_by = []
    plan["group_by"] = group_by
    filters = plan.get("filters") or []
    if not isinstance(filters, list):
        filters = [filters]
    if trend_tokens:
        has_month_filter = any(
            isinstance(filt, dict) and filt.get("field") == "month"
            for filt in filters
        )
        if not has_month_filter:
            trailing_range = trailing_year_range()
            filters = [*filters, trailing_range.to_filter()]
    plan["filters"] = _normalize_filters(question, filters)
    limit_value = plan.get("limit")
    if not top_intent:
        plan["limit"] = 0
    elif limit_value is None:
        plan["limit"] = 10
    order_by = plan.get("order_by")
    if order_by is None:
        plan["order_by"] = []
    return plan


def build_plan_rule_based(question: str) -> Dict[str, object]:
    bundle = load_synonyms()
    time_range = extract_time_range(question)
    metrics = ["incidents"]

    group_by = _detect_group_by(question, bundle)
    filters = _detect_filters(question, bundle, time_range)
    order_by = _detect_order(question)
    limit = _detect_limit(question)
    extras: Dict[str, object] = {}

    text_lower = question.lower()
    if any(token in text_lower for token in SHARE_TOKENS):
        extras["share_city"] = True
        if not order_by:
            order_by = [{"field": "incidents", "dir": "desc"}]

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
        extras=extras or None,
    )
    global _LAST_ENGINE
    _LAST_ENGINE = "rule_based"
    return _post_process_plan(question, plan.to_dict(), bundle)


def build_plan_llm(question: str) -> Dict[str, object]:
    global _LAST_ENGINE


    prompt = fill_time_tokens(PROMPT_PATH.read_text(encoding="utf-8"))
    semantic_yaml = SEMANTIC_PATH.read_text()
    columns = list_columns_for_prompt()

    # The LLM call itself can raise configuration errors; let them bubble up.
    raw = call_intent_llm(prompt, semantic_yaml, columns, question)


    try:
        plan = json.loads(raw)
        assert isinstance(plan.get("metrics", []), list)
        assert isinstance(plan.get("group_by", []), list)
        assert isinstance(plan.get("filters", []), list)
    except Exception as exc:  # pragma: no cover - defensive path
        raise RuntimeError(f"LLM returned non-JSON or invalid plan: {raw[:200]}...") from exc

    _LAST_ENGINE = "llm"
    bundle = load_synonyms()
    return _post_process_plan(question, plan, bundle)


def build_plan(question: str, prefer_llm: bool = True) -> Dict[str, object]:
    """Primary planner entry point with LLM fallback."""

    if not prefer_llm:
        return build_plan_rule_based(question)

    try:
        return build_plan_llm(question)
    except (LLMNotConfigured, RuntimeError):
        return build_plan_rule_based(question)
