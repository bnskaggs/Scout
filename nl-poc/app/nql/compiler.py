"""Compilation utilities for converting NQL into planner plans."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from .model import NQLQuery


def _current_month_start(today: Optional[date] = None) -> date:
    anchor = today or date.today()
    return date(anchor.year, anchor.month, 1)


def _shift_month(anchor: date, delta: int) -> date:
    year = anchor.year + ((anchor.month - 1 + delta) // 12)
    month = (anchor.month - 1 + delta) % 12 + 1
    return date(year, month, 1)


def _parse_date(raw: Optional[str], fallback_label: str) -> date:
    if not raw:
        raise ValueError(f"{fallback_label} must be provided")
    return datetime.fromisoformat(raw).date()


def _compile_time_filter(nql: NQLQuery, today: Optional[date]) -> Dict[str, Any]:
    window = nql.time.window
    time_field = "month"
    if window.type == "single_month":
        start = _parse_date(window.start, "single_month.start")
        end = _shift_month(start, 1)
        if not window.end:
            window.end = end.isoformat()
        if not window.exclusive_end:
            window.exclusive_end = True
        return {
            "field": time_field,
            "op": "between",
            "value": [start.isoformat(), end.isoformat()],
        }
    if window.type == "quarter":
        start = _parse_date(window.start, "quarter.start")
        end = _parse_date(window.end, "quarter.end")
        return {"field": time_field, "op": "between", "value": [start.isoformat(), end.isoformat()]}
    if window.type == "absolute":
        start = _parse_date(window.start, "absolute.start")
        if window.end:
            end = _parse_date(window.end, "absolute.end")
            return {"field": time_field, "op": "between", "value": [start.isoformat(), end.isoformat()]}
        return {"field": time_field, "op": ">=", "value": start.isoformat()}
    if window.type == "relative_months":
        end = _current_month_start(today)
        if window.end:
            end = _parse_date(window.end, "relative_months.end")
        months = window.n or 12
        start = _shift_month(end, -months)
        return {"field": time_field, "op": "between", "value": [start.isoformat(), end.isoformat()]}
    if window.type == "ytd":
        if window.end:
            end = _parse_date(window.end, "ytd.end")
        else:
            end = _shift_month(_current_month_start(today), 1)
        if window.start:
            start = _parse_date(window.start, "ytd.start")
        else:
            start = date(end.year if end.month > 1 else end.year - 1, 1, 1)
        return {"field": time_field, "op": "between", "value": [start.isoformat(), end.isoformat()]}
    raise ValueError(f"Unsupported time window type: {window.type}")


def _compile_filters(nql: NQLQuery, today: Optional[date]) -> List[Dict[str, Any]]:
    compiled: List[Dict[str, Any]] = []
    for filt in nql.filters:
        if filt.field == "month":
            continue
        compiled.append({"field": filt.field, "op": filt.op, "value": filt.value})
    compiled.append(_compile_time_filter(nql, today))
    return compiled


def _compile_group_by(nql: NQLQuery) -> List[str]:
    ordered: List[str] = []
    seen = set()
    for dim in [*nql.group_by, *nql.dimensions]:
        if not dim or dim in seen:
            continue
        ordered.append(dim)
        seen.add(dim)
    return ordered


def _compile_sort(nql: NQLQuery) -> List[Dict[str, str]]:
    order_by = [{"field": entry.by, "dir": entry.dir} for entry in nql.sort]
    if not order_by and nql.intent == "trend":
        order_by = [{"field": "month", "dir": "asc"}]
    return order_by


def _compile_compare(nql: NQLQuery) -> Optional[Dict[str, Any]]:
    if not nql.compare:
        return None
    compare_model = nql.compare
    compare: Dict[str, Any] = {}
    if compare_model.mode:
        compare["mode"] = compare_model.mode
        if compare_model.mode == "time":
            if compare_model.lhs_time:
                compare["lhs_time"] = compare_model.lhs_time
            if compare_model.rhs_time:
                compare["rhs_time"] = compare_model.rhs_time
        if compare_model.mode == "dimension" and compare_model.dimension:
            compare["dimension"] = compare_model.dimension
    if compare_model.type:
        periods = 1
        if compare_model.type == "yoy":
            periods = 12
        compare["type"] = compare_model.type
        compare["periods"] = periods
    if compare_model.baseline:
        compare["baseline"] = compare_model.baseline

    # v0.2 compare fields
    if nql.nql_version == "0.2":
        if compare_model.start:
            compare["start"] = compare_model.start
        if compare_model.end:
            compare["end"] = compare_model.end
        if compare_model.method:
            compare["method"] = compare_model.method

    if compare_model.internal_window:
        compare["internal_window"] = compare_model.internal_window.dict()
    return compare or None


def compile_nql_query(nql: NQLQuery, today: Optional[date] = None) -> Dict[str, Any]:
    """Compile an NQL query into the existing planner plan structure."""

    plan: Dict[str, Any] = {
        "metrics": [metric.alias for metric in nql.metrics],
        "group_by": _compile_group_by(nql),
        "filters": _compile_filters(nql, today),
        "order_by": _compile_sort(nql),
        "limit": nql.limit,
    }
    if nql.aggregate:
        plan["aggregate"] = nql.aggregate
    compare = _compile_compare(nql)
    if compare:
        plan["compare"] = compare

    # v0.2 fields
    if nql.nql_version == "0.2":
        if nql.panel_by:
            plan["panel_by"] = nql.panel_by
        if nql.bucket:
            plan["bucket"] = nql.bucket.dict()
        if nql.aggregate_v2:
            plan["aggregate_v2"] = nql.aggregate_v2.dict()
        if nql.top_k_within_group:
            plan["top_k_within_group"] = nql.top_k_within_group.dict()

    extras: Dict[str, Any] = {
        "rowcap_hint": nql.flags.rowcap_hint,
        "nql_compiled": True,
        "critic_pass": nql.provenance.critic_pass,
    }
    compile_info: Dict[str, Any] = {}
    if nql.metrics:
        compile_info["metricAlias"] = nql.metrics[0].alias
    compile_info["groupBy"] = list(nql.group_by)
    if compile_info:
        plan["compileInfo"] = compile_info
        extras["compileInfo"] = compile_info
    plan["extras"] = extras
    plan["_nql"] = nql.dict()
    plan["_critic_pass"] = nql.provenance.critic_pass
    return plan
