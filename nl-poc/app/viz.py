"""Chart specification helpers."""
from __future__ import annotations

from typing import Dict, List


def choose_chart(plan: Dict[str, object], records: List[Dict[str, object]]) -> Dict[str, object]:
    group_by = plan.get("group_by", [])
    compare = plan.get("compare")
    if not records:
        return {"type": "bar", "x": None, "y": None, "data": []}
    if group_by and group_by[0] == "month":
        return {
            "type": "line",
            "x": "month",
            "y": plan.get("metrics", ["incidents"])[0],
            "data": records,
        }
    if compare and "change_pct" in records[0]:
        return {
            "type": "bar",
            "x": group_by[0] if group_by else "value",
            "y": "change_pct",
            "data": records,
        }
    x_dim = group_by[0] if group_by else "value"
    y_metric = plan.get("metrics", ["incidents"])[0]
    return {"type": "bar", "x": x_dim, "y": y_metric, "data": records}


def build_narrative(plan: Dict[str, object], records: List[Dict[str, object]]) -> str:
    if not records:
        return "No data matched the request."

    metric = plan.get("metrics", ["incidents"])[0]
    compare = plan.get("compare")

    # For comparison queries, find the record with the highest change_pct
    # instead of just using records[0] (which may be sorted by incidents)
    if compare and any("change_pct" in rec for rec in records):
        # Filter to records with non-null change_pct and find max
        records_with_change = [r for r in records if r.get("change_pct") is not None]
        if records_with_change:
            top = max(records_with_change, key=lambda r: r.get("change_pct", float("-inf")))
        else:
            top = records[0]
    else:
        top = records[0]

    parts = []
    group_by = plan.get("group_by") or []
    if group_by:
        metric_candidates = plan.get("metrics") or []
        metric_alias = metric_candidates[0] if metric_candidates else metric

        label = "Unknown"
        resolved_dim = None
        for dim in group_by:
            if isinstance(dim, dict):
                dim_keys = [
                    dim.get("alias"),
                    dim.get("field"),
                    dim.get("expr"),
                ]
            else:
                dim_keys = [dim]
            resolved_dim = next((key for key in dim_keys if key and key in top), None)
            if resolved_dim:
                label = top.get(resolved_dim, "Unknown")
                break
        if not resolved_dim:
            resolved_dim = next(
                (
                    key
                    for key in top.keys()
                    if key not in metric_candidates and key not in {metric, "change_pct"}
                ),
                None,
            )
            if resolved_dim:
                label = top.get(resolved_dim, "Unknown")

        value = top.get(metric_alias if metric_alias in top else metric)
        if value is None:
            value = top.get(metric)

        # Check if this is a "bottom/lowest" query (ascending sort order)
        order_by = plan.get("order_by", [])
        is_ascending = any(
            isinstance(o, dict) and o.get("dir") == "asc"
            for o in order_by
        )

        if is_ascending:
            parts.append(f"{label} had the fewest with {value} incidents")
        else:
            parts.append(f"{label} led with {value} incidents")
    else:
        metric_name = metric.replace("_", " ")
        value = top.get(metric)
        if value is None and plan.get("metrics"):
            fallback_metric = plan["metrics"][0]
            value = top.get(fallback_metric)
        parts.append(f"Total {metric_name} was {value}")

    if compare and "change_pct" in top and top["change_pct"] is not None:
        direction = "up" if top["change_pct"] > 0 else "down"
        pct_value = abs(round(top['change_pct'], 1))  # SQL already multiplied by 100
        parts.append(f"({direction} {pct_value}% vs prior period)")

    return "; ".join(parts) + "."
