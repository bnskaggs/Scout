"""SQL and narrative guardrails for the prototype."""
from __future__ import annotations

import copy
import datetime as _dt
import math
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


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


def _default_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    base = {
        "MAX_ROWS": 10_000,
        "TOP_K_DEFAULT": 100,
        "JOIN_BLOWUP_FACTOR": 10,
        "MAX_TIME_RANGE_YEARS": 10,
        "DEFAULT_LIMIT": 100,
        "canonical_values": {},
    }
    if not config:
        return base
    merged = base.copy()
    merged.update(config)
    if "canonical_values" not in merged or merged["canonical_values"] is None:
        merged["canonical_values"] = {}
    return merged


def _copy_nql(nql: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not nql:
        return {}
    return copy.deepcopy(nql)


def _estimate_groups(
    group_by: Sequence[str],
    distinct_counts: Optional[Dict[str, Any]],
    join_cardinality_est: Optional[float],
) -> Optional[float]:
    if not group_by or not distinct_counts:
        return None
    estimate = 1.0
    for dim in group_by:
        value = distinct_counts.get(dim)
        if value is None:
            return None
        try:
            cardinality = float(value)
        except (TypeError, ValueError):
            return None
        if cardinality <= 0:
            return None
        estimate *= cardinality
        if estimate > 1e12:  # Prevent runaway numbers
            return estimate
    if join_cardinality_est:
        try:
            estimate *= float(join_cardinality_est)
        except (TypeError, ValueError):
            pass
    return estimate


def _has_join_without_equality(sql: str) -> bool:
    join_iter = re.finditer(
        r"\bjoin\b\s+.*?\b(on|using)\b(.*?)(?=\bjoin\b|\bwhere\b|$)",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    found_join = False
    for match in join_iter:
        found_join = True
        keyword = match.group(1).lower()
        clause = match.group(2)
        if keyword == "using":
            continue
        if "=" not in clause:
            return True
    if not found_join and re.search(r"\bjoin\b", sql, re.IGNORECASE):
        # JOIN present but failed to capture ON clause
        return True
    return False


def _largest_base_table(preview_stats: Optional[Dict[str, Any]]) -> Optional[float]:
    if not preview_stats:
        return None
    candidates: List[float] = []
    for key in ("base_table_row_counts", "table_row_counts", "table_stats"):
        value = preview_stats.get(key)
        if isinstance(value, dict):
            for item in value.values():
                try:
                    candidates.append(float(item))
                except (TypeError, ValueError):
                    continue
        elif isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, (int, float)):
                    candidates.append(float(item))
                elif isinstance(item, dict):
                    for subval in item.values():
                        try:
                            candidates.append(float(subval))
                        except (TypeError, ValueError):
                            continue
    alt = preview_stats.get("row_count_est")
    if isinstance(alt, (int, float)):
        candidates.append(float(alt))
    if not candidates:
        return None
    return max(candidates)


def _ensure_limit(nql: Dict[str, Any], default_limit: int) -> None:
    limit = nql.get("limit")
    if limit is None:
        nql["limit"] = default_limit


def _normalize_number_string(token: str) -> Tuple[Optional[float], bool]:
    text = token.strip()
    if not text:
        return None, False
    is_percent = text.endswith("%")
    cleaned = text.rstrip("%")
    cleaned = cleaned.replace(",", "")
    try:
        value = float(cleaned)
        return value, is_percent
    except ValueError:
        return None, is_percent


def _extract_numbers_from_text(text: str) -> List[str]:
    pattern = r"[+-]?\d+(?:,\d{3})*(?:\.\d+)?%?"
    return re.findall(pattern, text or "")


def _collect_numeric_values(rows: Iterable[Dict[str, Any]]) -> List[Tuple[float, bool]]:
    values: List[Tuple[float, bool]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for value in row.values():
            if isinstance(value, (int, float)):
                values.append((float(value), False))
            elif isinstance(value, str):
                for token in _extract_numbers_from_text(value):
                    parsed, is_percent = _normalize_number_string(token)
                    if parsed is not None:
                        values.append((parsed, is_percent))
            elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
                # Recurse shallowly for nested values such as lists/tuples
                nested_rows = []
                for item in value:
                    if isinstance(item, dict):
                        nested_rows.append(item)
                    elif isinstance(item, (int, float)):
                        values.append((float(item), False))
                    elif isinstance(item, str):
                        for token in _extract_numbers_from_text(item):
                            parsed, is_percent = _normalize_number_string(token)
                            if parsed is not None:
                                values.append((parsed, is_percent))
                if nested_rows:
                    values.extend(_collect_numeric_values(nested_rows))
    return values


def validate_plan(
    nql: Optional[Dict[str, Any]],
    sql: str,
    preview_stats: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cfg = _default_config(config)
    diagnostics: List[Dict[str, Any]] = []
    effective_nql = _copy_nql(nql)
    effective_sql = sql
    limits = {
        "row_cap": cfg["MAX_ROWS"],
        "applied": False,
        "top_k": None,
    }
    decision = "allow"

    # SELECT * safety check
    if _SELECT_STAR.search(sql or ""):
        diagnostics.append(
            {
                "type": "unsafe_select_star",
                "message": "SELECT * detected. Explicit column selection required.",
                "details": {},
            }
        )
        return {
            "decision": "block",
            "effective_nql": effective_nql,
            "effective_sql": None,
            "diagnostics": diagnostics,
            "limits": limits,
            "postflight_numeric_ok": True,
        }

    # Time sanity checks
    time_spec = (effective_nql or {}).get("time") or {}
    start = time_spec.get("start") if isinstance(time_spec, dict) else None
    end = time_spec.get("end") if isinstance(time_spec, dict) else None
    parsed_start: Optional[_dt.date] = None
    parsed_end: Optional[_dt.date] = None
    if start and end:
        try:
            parsed_start = _dt.date.fromisoformat(str(start))
            parsed_end = _dt.date.fromisoformat(str(end))
        except ValueError:
            parsed_start = None
            parsed_end = None
    if not parsed_start or not parsed_end:
        diagnostics.append(
            {
                "type": "ambiguous_time",
                "message": "Time range must include valid start and end dates.",
                "details": {"start": start, "end": end},
            }
        )
        return {
            "decision": "block",
            "effective_nql": effective_nql,
            "effective_sql": None,
            "diagnostics": diagnostics,
            "limits": limits,
            "postflight_numeric_ok": True,
        }

    if parsed_end <= parsed_start:
        diagnostics.append(
            {
                "type": "ambiguous_time",
                "message": "End date must be after start date.",
                "details": {"start": start, "end": end},
            }
        )
        return {
            "decision": "block",
            "effective_nql": effective_nql,
            "effective_sql": None,
            "diagnostics": diagnostics,
            "limits": limits,
            "postflight_numeric_ok": True,
        }

    if (parsed_end - parsed_start).days > cfg["MAX_TIME_RANGE_YEARS"] * 366:
        diagnostics.append(
            {
                "type": "ambiguous_time",
                "message": "Time range exceeds maximum allowed span.",
                "details": {
                    "start": start,
                    "end": end,
                    "max_years": cfg["MAX_TIME_RANGE_YEARS"],
                },
            }
        )
        # Suggest safe rewrite to last 12 months
        safe_end = parsed_end
        safe_start = parsed_end - _dt.timedelta(days=365)
        effective_nql.setdefault("time", {})["start"] = safe_start.isoformat()
        effective_nql["time"]["end"] = safe_end.isoformat()
        diagnostics.append(
            {
                "type": "blocked_query",
                "message": "Suggested rewrite: snap to last 12 months.",
                "details": {
                    "suggested_start": safe_start.isoformat(),
                    "suggested_end": safe_end.isoformat(),
                },
            }
        )
        return {
            "decision": "block",
            "effective_nql": effective_nql,
            "effective_sql": None,
            "diagnostics": diagnostics,
            "limits": limits,
            "postflight_numeric_ok": True,
        }

    # Join explosion checks
    join_blowup_factor = cfg["JOIN_BLOWUP_FACTOR"]
    join_cardinality = None
    if preview_stats and isinstance(preview_stats.get("join_cardinality_est"), (int, float)):
        join_cardinality = float(preview_stats["join_cardinality_est"])

    if _has_join_without_equality(sql or ""):
        diagnostics.append(
            {
                "type": "join_cardinality_exceeded",
                "message": "Join detected without equality predicate.",
                "details": {
                    "suggestions": [
                        "Add equality predicate on join keys.",
                        "Push down time filters before the join.",
                    ]
                },
            }
        )
        diagnostics.append(
            {
                "type": "blocked_query",
                "message": "Execution blocked due to unsafe join.",
                "details": {
                    "recommended_patch": "Add join predicates or remove the join."
                },
            }
        )
        return {
            "decision": "block",
            "effective_nql": effective_nql,
            "effective_sql": None,
            "diagnostics": diagnostics,
            "limits": limits,
            "postflight_numeric_ok": True,
        }

    if join_cardinality is not None:
        largest_base = _largest_base_table(preview_stats)
        if largest_base and join_cardinality > join_blowup_factor * largest_base:
            diagnostics.append(
                {
                    "type": "join_cardinality_exceeded",
                    "message": "Join cardinality estimate exceeds safety threshold.",
                    "details": {
                        "join_cardinality_est": join_cardinality,
                        "largest_base_table": largest_base,
                        "threshold": join_blowup_factor,
                    },
                }
            )
            diagnostics.append(
                {
                    "type": "blocked_query",
                    "message": "Execution blocked. Reduce scope or constrain joins.",
                    "details": {
                        "recommended_patch": "Add equality predicate, tighten time range, or limit dimension values.",
                    },
                }
            )
            return {
                "decision": "block",
                "effective_nql": effective_nql,
                "effective_sql": None,
                "diagnostics": diagnostics,
                "limits": limits,
                "postflight_numeric_ok": True,
            }

    # Apply row cap rewrites if needed
    group_by: List[str] = []
    if isinstance(effective_nql.get("group_by"), list):
        group_by = list(effective_nql.get("group_by", []))
    distinct_counts = None
    if preview_stats and isinstance(preview_stats.get("distinct_counts"), dict):
        distinct_counts = preview_stats["distinct_counts"]
    estimated_groups = _estimate_groups(group_by, distinct_counts, join_cardinality)
    rowcap_modified = False
    top_k_applied: Optional[int] = None

    if estimated_groups and estimated_groups > cfg["MAX_ROWS"]:
        if len(group_by) > 1:
            kept = group_by[:1]
            removed = group_by[1:]
            effective_nql["group_by"] = kept
            diagnostics.append(
                {
                    "type": "row_cap_exceeded",
                    "message": (
                        "Expected fan-out exceeds row cap; keeping only first group_by dimension."
                    ),
                    "details": {
                        "estimated_groups": math.ceil(estimated_groups),
                        "dropped": removed,
                        "kept": kept,
                    },
                }
            )
            rowcap_modified = True
            group_by = kept
            estimated_groups = _estimate_groups(group_by, distinct_counts, join_cardinality)
        if not estimated_groups or estimated_groups > cfg["MAX_ROWS"]:
            top_k_applied = cfg["TOP_K_DEFAULT"]
            existing_limit = effective_nql.get("limit")
            if not isinstance(existing_limit, int) or existing_limit > top_k_applied:
                effective_nql["limit"] = top_k_applied
            diagnostics.append(
                {
                    "type": "row_cap_exceeded",
                    "message": "Applied TOP-K to enforce row cap safety.",
                    "details": {
                        "estimated_groups": math.ceil(estimated_groups) if estimated_groups else None,
                        "top_k": top_k_applied,
                    },
                }
            )
            limits["top_k"] = top_k_applied
            rowcap_modified = True

    if rowcap_modified:
        limits["applied"] = True
        decision = "rewrite"

    # Unknown value fallback via LIKE
    canonical = cfg.get("canonical_values") or {}
    filters = []
    if isinstance(effective_nql.get("filters"), list):
        filters = effective_nql.get("filters", [])
    for flt in filters:
        if not isinstance(flt, dict):
            continue
        column = flt.get("field") or flt.get("column")
        value = flt.get("value")
        if not column or not isinstance(value, str):
            continue
        known_values = canonical.get(column) if isinstance(canonical, dict) else None
        if not known_values:
            continue
        if value in known_values:
            continue
        matches = [v for v in known_values if value.lower() in str(v).lower()][:5]
        flt["op"] = "ilike"
        flt["value"] = f"%{value}%"
        diagnostics.append(
            {
                "type": "unknown_value_fallback",
                "message": f"Falling back to ILIKE match for {column}.",
                "details": {
                    "column": column,
                    "value": value,
                    "matches": matches,
                },
            }
        )

    # Ensure a sensible limit exists for detail tables
    _ensure_limit(effective_nql, cfg["DEFAULT_LIMIT"])

    return {
        "decision": decision,
        "effective_nql": effective_nql,
        "effective_sql": effective_sql,
        "diagnostics": diagnostics,
        "limits": limits,
        "postflight_numeric_ok": True,
    }


def apply_rewrites(guardrail_json: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "nql": guardrail_json.get("effective_nql"),
        "sql": guardrail_json.get("effective_sql"),
    }


def validate_narrative_numbers(
    text: str,
    result_rows: Optional[Sequence[Dict[str, Any]]],
) -> Dict[str, Any]:
    numbers_in_text = _extract_numbers_from_text(text or "")
    if not numbers_in_text:
        return {"ok": True, "missing_numbers": []}

    table_values = _collect_numeric_values(result_rows or [])
    if not table_values:
        return {"ok": False, "missing_numbers": numbers_in_text}

    missing: List[str] = []
    for token in numbers_in_text:
        parsed, is_percent = _normalize_number_string(token)
        if parsed is None:
            continue
        tolerance = 0.5 if abs(parsed) >= 1 else 0.01
        if is_percent:
            tolerance = 0.1
        match_found = False
        for value, value_is_percent in table_values:
            if value_is_percent != is_percent:
                continue
            if abs(value - parsed) <= tolerance:
                match_found = True
                break
        if not match_found:
            missing.append(token)

    return {"ok": not missing, "missing_numbers": missing}
