"""SQL builder for the NL analytics prototype."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from .resolver import SemanticModel


def quote_identifier(name: str) -> str:
    if name.startswith('"') and name.endswith('"'):
        return name
    return f'"{name}"'


def dimension_expression(dimension_name: str, semantic: SemanticModel, alias: str = "") -> str:
    dim = semantic.dimensions[dimension_name]
    prefix = f"{alias}." if alias else ""
    if dimension_name == "month":
        return f"{prefix}month" if alias else "month"
    column = dim.column
    return f"{prefix}{quote_identifier(column)}"


def _format_literal(value) -> str:
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return "NULL"
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def _build_filters(filters: List[Dict[str, object]], semantic: SemanticModel, alias: str = "") -> str:
    clauses: List[str] = []
    for filt in filters:
        field = filt.get("field")
        op = filt.get("op", "=")
        value = filt.get("value")
        if field == "month":
            month_expr = dimension_expression("month", semantic, alias)
            if isinstance(value, (list, tuple)) and len(value) >= 2 and value[0] and value[1]:
                start, end = value[0], value[1]
                if start == end:
                    clauses.append(f"{month_expr} = DATE '{start}'")
                else:
                    try:
                        start_dt = datetime.fromisoformat(str(start))
                        end_dt = datetime.fromisoformat(str(end))
                    except ValueError:
                        start_dt = end_dt = None
                    if start_dt and end_dt and start_dt == end_dt:
                        clauses.append(f"{month_expr} = DATE '{start}'")
                    else:
                        clauses.append(
                            f"{month_expr} >= DATE '{start}' AND {month_expr} < DATE '{end}'"
                        )
            elif isinstance(value, (list, tuple)) and value:
                clauses.append(f"{month_expr} = DATE '{value[0]}'")
            elif isinstance(value, str):
                clauses.append(f"{month_expr} = DATE '{value}'")
            continue
        if field not in semantic.dimensions:
            continue
        expr = dimension_expression(field, semantic, alias)
        if op == "in" and isinstance(value, list):
            joined = ", ".join(_format_literal(v) for v in value)
            clauses.append(f"{expr} IN ({joined})")
        elif op == "between" and isinstance(value, list) and len(value) == 2:
            clauses.append(f"{expr} BETWEEN {_format_literal(value[0])} AND {_format_literal(value[1])}")
        elif op == "like_any" and isinstance(value, list):
            lowered = [str(v).lower() for v in value if v]
            if lowered:
                like_clauses = [f"LOWER({expr}) LIKE {_format_literal(pattern)}" for pattern in lowered]
                clauses.append("(" + " OR ".join(like_clauses) + ")")
        else:
            clauses.append(f"{expr} {op} {_format_literal(value)}")
    if not clauses:
        return ""
    return "WHERE " + " AND ".join(clauses)


def build(plan: Dict[str, object], semantic: SemanticModel) -> str:
    metrics = plan.get("metrics", []) or ["incidents"]
    group_by = plan.get("group_by", [])
    filters = plan.get("filters", [])
    order_by = plan.get("order_by") or []
    raw_limit = plan.get("limit", 0)
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        limit = 0
    compare = plan.get("compare")
    compare_dict = compare if isinstance(compare, dict) else {}
    compare_type = compare_dict.get("type")
    internal_window = compare_dict.get("internal_window") if compare_type == "mom" else None
    extras = plan.get("extras") or {}

    base_cte = "WITH base AS (SELECT DATE_TRUNC('month', \"DATE OCC\") AS month, * FROM la_crime_raw)"

    select_parts: List[str] = []
    group_exprs: List[str] = []
    for dim in group_by:
        expr = dimension_expression(dim, semantic, alias="base")
        select_parts.append(f"{expr} AS {dim}")
        group_exprs.append(expr)

    metric_exprs: List[str] = []
    for metric in metrics:
        metric_obj = semantic.metrics[metric]
        metric_exprs.append(f"{metric_obj.sql_expression()} AS {metric}")

    if not metric_exprs:
        metric_exprs.append("COUNT(*) AS incidents")

    select_clause = ", ".join(select_parts + metric_exprs)
    where_clause = _build_filters(filters, semantic, alias="base")
    agg_filters = filters
    agg_where_clause = where_clause
    if internal_window:
        month_replaced = False
        updated_filters: List[Dict[str, object]] = []
        for filt in filters:
            if isinstance(filt, dict) and filt.get("field") == "month":
                if not month_replaced:
                    updated_filters.append(internal_window)
                    month_replaced = True
                continue
            updated_filters.append(filt)
        if not month_replaced:
            updated_filters.append(internal_window)
        agg_filters = updated_filters
        agg_where_clause = _build_filters(agg_filters, semantic, alias="base")

    group_clause = ""
    if group_exprs:
        group_clause = "GROUP BY " + ", ".join(group_exprs)

    if not order_by and "month" in group_by:
        order_by = [{"field": "month", "dir": "asc"}]
    if not order_by and compare_type in {"mom", "yoy"}:
        order_by = [{"field": "month", "dir": "asc"}]

    if compare_type in {"mom", "yoy"}:
        lag_period = compare_dict.get("periods", 1)
        agg_select = select_parts.copy()
        month_expr = dimension_expression("month", semantic, alias="base")
        agg_select.append(f"{month_expr} AS month")
        agg_metrics = ["COUNT(*) AS incidents"]
        agg_filters = filters
        internal_window = None
        if compare.get("type") == "mom":
            internal_window = plan.get("internal_window")
            if internal_window:
                replaced = False
                agg_filters = []
                for filt in filters:
                    if filt.get("field") == "month":
                        agg_filters.append(internal_window)
                        replaced = True
                    else:
                        agg_filters.append(filt)
                if not replaced:
                    agg_filters.append(internal_window)
        if internal_window:
            agg_where_clause = _build_filters(agg_filters, semantic, alias="base")
        else:
            agg_where_clause = where_clause
        agg_sql = f"SELECT {', '.join(agg_select + agg_metrics)} FROM base"
        agg_group_exprs = group_exprs.copy()
        if month_expr not in agg_group_exprs:
            agg_group_exprs.append(month_expr)
        if agg_where_clause:
            agg_sql += f" {agg_where_clause}"
        if agg_group_exprs:
            agg_sql += " GROUP BY " + ", ".join(agg_group_exprs)
        partition_clause = _build_partition_clause(group_by)
        compare_sql = (
            f"{base_cte}, aggregated AS ({agg_sql}), ranked AS ("
            f"SELECT aggregated.*, LAG(incidents, {lag_period}) OVER ({partition_clause} ORDER BY month) AS prior_incidents "
            "FROM aggregated)"
        )
        dim_prefix = ", ".join(group_by)
        prefix = f"{dim_prefix}, " if dim_prefix else ""
        final_sql = (
            f"{compare_sql} SELECT {prefix}incidents, CASE WHEN prior_incidents IS NULL OR prior_incidents = 0 THEN NULL "
            "ELSE (incidents - prior_incidents) * 100.0 / prior_incidents END AS change_pct, month FROM ranked"
        )
        if internal_window:

            month_filters = [filt for filt in filters if filt.get("field") == "month"]
            month_clause = _build_filters(month_filters, semantic) if month_filters else ""
            if month_clause:
                final_sql += f" {month_clause}"

        if order_by:
            final_sql += f" {_build_order_clause(order_by)}"
        if limit:
            final_sql += f" LIMIT {limit}"
        return final_sql

    agg_query = f"SELECT {select_clause} FROM base"
    if where_clause:
        agg_query += f" {where_clause}"
    if group_clause:
        agg_query += f" {group_clause}"

    share_requested = bool(extras.get("share_city")) and _is_single_month_equality(filters)
    if compare:
        share_requested = False

    if share_requested:
        cte_sql = f"{base_cte}, aggregated AS ({agg_query})"
        final_select_parts = []
        for dim in group_by:
            final_select_parts.append(dim)
        for metric in metrics:
            final_select_parts.append(metric)
        final_select_parts.append(
            "incidents * 1.0 / NULLIF(SUM(incidents) OVER (), 0) AS share_city"
        )
        sql = f"{cte_sql} SELECT {', '.join(final_select_parts)} FROM aggregated"
    else:
        sql = f"{base_cte} {agg_query}"

    if order_by:
        sql += f" {_build_order_clause(order_by)}"
    if limit:
        sql += f" LIMIT {limit}"
    return sql


def _build_partition_clause(group_by: List[str]) -> str:
    dims = [dim for dim in group_by if dim != "month"]
    if not dims:
        return "PARTITION BY 1"
    return "PARTITION BY " + ", ".join(dims)


def _build_order_clause(order_by: List[Dict[str, str]]) -> str:
    if not order_by:
        return ""
    order = order_by[0]
    field = order.get("field")
    direction = order.get("dir", "desc").upper()
    return f"ORDER BY {field} {direction}"


def _is_single_month_equality(filters: List[Dict[str, object]]) -> bool:
    for filt in filters:
        if filt.get("field") != "month":
            continue
        op = filt.get("op")
        value = filt.get("value")
        if op == "=" and value:
            return True
        if isinstance(value, list) and len(value) == 1:
            return True
        if isinstance(value, list) and len(value) >= 2 and value[0] and value[1]:
            try:
                start = datetime.strptime(value[0], "%Y-%m-%d")
                end = datetime.strptime(value[1], "%Y-%m-%d")
            except (TypeError, ValueError):
                continue
            if (end.year == start.year and end.month == start.month + 1) or (
                start.month == 12 and end.year == start.year + 1 and end.month == 1
            ):
                return True
    return False
