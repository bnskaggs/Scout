"""SQL builder for the NL analytics prototype."""
from __future__ import annotations

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
                clauses.append(
                    f"{month_expr} >= DATE '{value[0]}' AND {month_expr} < DATE '{value[1]}'"
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
        else:
            clauses.append(f"{expr} {op} {_format_literal(value)}")
    if not clauses:
        return ""
    return "WHERE " + " AND ".join(clauses)


def build(plan: Dict[str, object], semantic: SemanticModel) -> str:
    metrics = plan.get("metrics", []) or ["incidents"]
    group_by = plan.get("group_by", [])
    filters = plan.get("filters", [])
    order_by = plan.get("order_by", [])
    limit = plan.get("limit", 50)
    compare = plan.get("compare")

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

    group_clause = ""
    if group_exprs:
        group_clause = "GROUP BY " + ", ".join(group_exprs)

    if compare and compare.get("type") in {"mom", "yoy"}:
        lag_period = compare.get("periods", 1)
        agg_select = select_parts.copy()
        month_expr = dimension_expression("month", semantic, alias="base")
        agg_select.append(f"{month_expr} AS month")
        agg_metrics = ["COUNT(*) AS incidents"]
        agg_sql = f"SELECT {', '.join(agg_select + agg_metrics)} FROM base"
        agg_group_exprs = group_exprs.copy()
        if month_expr not in agg_group_exprs:
            agg_group_exprs.append(month_expr)
        if where_clause:
            agg_sql += f" {where_clause}"
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
        if order_by:
            final_sql += f" {_build_order_clause(order_by)}"
        if limit:
            final_sql += f" LIMIT {limit}"
        return final_sql

    sql = f"{base_cte} SELECT {select_clause} FROM base"
    if where_clause:
        sql += f" {where_clause}"
    if group_clause:
        sql += f" {group_clause}"
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
