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
    top = records[0]
    metric = plan.get("metrics", ["incidents"])[0]
    compare = plan.get("compare")
    parts = []
    if plan.get("group_by"):
        first_dim = plan["group_by"][0]
        label = top.get(first_dim, "Unknown")
        value = top.get(metric)
        parts.append(f"{label} led with {value} incidents")
    else:
        value = top.get(metric)
        parts.append(f"There were {value} incidents")
    if compare and "change_pct" in top and top["change_pct"] is not None:
        direction = "up" if top["change_pct"] > 0 else "down"
        parts.append(f"({direction} {abs(round(top['change_pct'], 1))}% vs prior period)")
    return "; ".join(parts) + "."
