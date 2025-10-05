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
        return "No incidents found for the selected period."

    compare = plan.get("compare")
    compile_info = {}
    extras = plan.get("extras") or {}
    if isinstance(plan.get("compileInfo"), dict):
        compile_info = plan["compileInfo"]
    elif isinstance(extras.get("compileInfo"), dict):
        compile_info = extras["compileInfo"]

    def _first_entry(value):
        if isinstance(value, (list, tuple)):
            return value[0] if value else None
        return value

    dim = _first_entry(compile_info.get("groupBy"))
    if dim is None:
        dim = _first_entry(plan.get("group_by") or [])

    metric_alias = compile_info.get("metricAlias")
    metrics = plan.get("metrics") or []
    if not metric_alias and metrics:
        metric_alias = metrics[0]

    def _first_numeric_column(rows: List[Dict[str, object]], exclude: set) -> str:
        for row in rows:
            for key, value in row.items():
                if key in exclude:
                    continue
                if isinstance(value, bool):
                    continue
                if isinstance(value, (int, float)):
                    return key
        return ""

    exclude_keys = {dim, "change_pct", "change_pct_formatted"}
    metric_key = metric_alias or _first_numeric_column(records, {k for k in exclude_keys if k}) or "count"

    order_by = plan.get("order_by", [])
    is_ascending = any(
        isinstance(o, dict) and o.get("dir") == "asc"
        for o in order_by
    )

    selected_by_change = False
    if compare and any("change_pct" in rec for rec in records):
        records_with_change = [r for r in records if r.get("change_pct") is not None]
        if records_with_change:
            top = max(records_with_change, key=lambda r: r.get("change_pct", float("-inf")))
            selected_by_change = True
        else:
            top = records[0]
    else:
        top = records[0]

    sorted_locally = False
    if dim and not selected_by_change:
        def _metric_value(row: Dict[str, object]) -> float:
            value = row.get(metric_key)
            if isinstance(value, bool) or value is None:
                return float("inf") if is_ascending else float("-inf")
            if isinstance(value, (int, float)):
                return float(value)
            try:
                return float(value)
            except (TypeError, ValueError):
                return float("inf") if is_ascending else float("-inf")

        def _dim_label(row: Dict[str, object]) -> str:
            label_value = row.get(dim)
            if label_value is None:
                return ""
            return str(label_value)

        if is_ascending:
            sorted_rows = sorted(
                records,
                key=lambda r: (_metric_value(r), _dim_label(r)),
            )
        else:
            sorted_rows = sorted(
                records,
                key=lambda r: (-_metric_value(r), _dim_label(r)),
            )
        if sorted_rows:
            sorted_locally = sorted_rows[0] is not records[0]
            top = sorted_rows[0]

    parts: List[str] = []

    if dim:
        label_value = top.get(dim, "Unknown")
        if label_value in (None, ""):
            label = "Unknown"
        else:
            label = str(label_value)
        metric_value = top.get(metric_key)
        if metric_value is None:
            metric_value = 0
        if is_ascending:
            parts.append(f"{label} had the fewest with {metric_value} incidents")
        else:
            parts.append(f"{label} led with {metric_value} incidents")
    else:
        metric_name = (metric_key or "count").replace("_", " ")
        total_row = top
        metric_value = total_row.get(metric_key)
        if metric_value is None:
            metric_value = 0
        parts.append(f"Total {metric_name}: {metric_value}")

    if compare and "change_pct" in top and top["change_pct"] is not None:
        direction = "up" if top["change_pct"] > 0 else "down"
        pct_raw = top["change_pct"]
        if isinstance(pct_raw, (int, float)):
            scaled = pct_raw * 100 if -1 < pct_raw < 1 else pct_raw
        else:
            try:
                pct_numeric = float(pct_raw)
            except (TypeError, ValueError):  # pragma: no cover - defensive
                pct_numeric = 0
            scaled = pct_numeric * 100 if -1 < pct_numeric < 1 else pct_numeric
        pct_value = abs(round(scaled, 1))
        parts.append(f"({direction} {pct_value}% vs prior period)")

    if sorted_locally:
        diagnostics = plan.setdefault("diagnostics", [])
        if not any(d.get("type") == "header_local_sort" for d in diagnostics if isinstance(d, dict)):
            diagnostics.append(
                {
                    "type": "header_local_sort",
                    "message": "Rows locally sorted by metric desc for header consistency",
                }
            )

    return "; ".join(parts) + "."
