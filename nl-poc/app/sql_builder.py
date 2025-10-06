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

        # Handle raw date range filtering (for pre/post absolute compare)
        if field == "_date_range" or filt.get("_raw_date"):
            prefix = f"{alias}." if alias else ""
            date_col = f'{prefix}"DATE OCC"'
            if op == "between" and isinstance(value, list) and len(value) == 2:
                start, end = value[0], value[1]
                clauses.append(f"{date_col} >= DATE '{start}' AND {date_col} < DATE '{end}'")
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
    aggregate = plan.get("aggregate")
    raw_metrics = [metric for metric in (plan.get("metrics") or []) if isinstance(metric, str)]
    metrics = raw_metrics.copy()
    if not metrics and aggregate != "count":
        metrics = ["incidents"]
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

    # v0.2 features
    panel_by = plan.get("panel_by")
    bucket = plan.get("bucket")
    aggregate_v2 = plan.get("aggregate_v2")
    top_k_within_group = plan.get("top_k_within_group")

    base_cte = "WITH base AS (SELECT DATE_TRUNC('month', \"DATE OCC\") AS month, * FROM la_crime_raw)"

    # Route to v0.2 SQL builders if features present
    if top_k_within_group and isinstance(top_k_within_group, dict):
        return _build_v2_topk_within_group_sql(
            base_cte, top_k_within_group, filters, group_by, metrics, semantic, limit
        )

    if bucket and isinstance(bucket, dict):
        return _build_v2_bucket_sql(base_cte, bucket, filters, metrics, semantic, limit)

    if aggregate_v2 and isinstance(aggregate_v2, dict):
        return _build_v2_aggregate_sql(base_cte, aggregate_v2, filters, group_by, semantic, limit)

    # Check for v0.2 compare with baseline
    if compare_dict.get("baseline") in ("previous_period", "same_period_last_year", "absolute"):
        if compare_dict.get("method") in ("diff_abs", "diff_pct"):
            return _build_v2_compare_sql(
                base_cte, compare_dict, filters, group_by, metrics, semantic, order_by, limit
            )

    select_parts: List[str] = []
    group_exprs: List[str] = []
    for dim in group_by:
        expr = dimension_expression(dim, semantic, alias="base")
        select_parts.append(f"{expr} AS {dim}")
        group_exprs.append(expr)

    metric_exprs: List[str] = []
    metric_aliases: List[str] = []
    if aggregate == "count":
        metric_exprs.append("COUNT(*) AS count")
        metric_aliases.append("count")
    else:
        for metric in metrics:
            if metric in {"count", "*"}:
                metric_exprs.append("COUNT(*) AS count")
                metric_aliases.append("count")
                continue
            metric_obj = semantic.metrics[metric]
            metric_exprs.append(f"{metric_obj.sql_expression()} AS {metric}")
            metric_aliases.append(metric)

    if not metric_exprs:
        metric_exprs.append("COUNT(*) AS incidents")
        metric_aliases.append("incidents")

    select_clause = ", ".join(select_parts + metric_exprs)
    where_clause = _build_filters(filters, semantic, alias="base")
    agg_filters = filters
    agg_where_clause = where_clause

    # Bug fix: Only extend time window if compare operator is actually present
    # This prevents "Trend in 2023" from starting at Dec 2022
    if internal_window and compare_type == "mom":
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

    # Bug fix: Compare panels ordering - ensure panel_by dimension is sorted properly
    if not order_by and "month" in group_by:
        order_by = [{"field": "month", "dir": "asc"}]
        # If panel_by is present, add secondary sort by panel dimension
        if panel_by and panel_by in group_by:
            order_by.append({"field": panel_by, "dir": "asc"})
    if not order_by and compare_type in {"mom", "yoy"}:
        order_by = [{"field": "month", "dir": "asc"}]
    # If panel_by is present but not month, sort by panel_by first
    if not order_by and panel_by and panel_by in group_by:
        order_by = [{"field": panel_by, "dir": "asc"}]

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
        metric_alias = metric_aliases[0] if metric_aliases else "incidents"
        for dim in group_by:
            final_select_parts.append(dim)
        for metric in metric_aliases:
            final_select_parts.append(metric)
        final_select_parts.append(
            f"{metric_alias} * 1.0 / NULLIF(SUM({metric_alias}) OVER (), 0) AS share_city"
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
    """Build ORDER BY clause from list of sort specs.

    Bug fix: Support multiple sort columns for compare panels.
    Example: ORDER BY month ASC, area ASC
    """
    if not order_by:
        return ""

    order_parts = []
    for order in order_by:
        field = order.get("field")
        direction = order.get("dir", "desc").upper()
        order_parts.append(f"{field} {direction}")

    return "ORDER BY " + ", ".join(order_parts)


def _shift_month_filter(filters: List[Dict[str, object]], delta_months: int) -> List[Dict[str, object]]:
    """Shift month filter by delta_months. Returns new filter list with shifted month."""
    from datetime import date, datetime

    shifted_filters = []
    for filt in filters:
        if filt.get("field") != "month":
            shifted_filters.append(filt)
            continue

        # Extract current month from filter
        value = filt.get("value")
        if isinstance(value, list) and len(value) >= 2:
            start_str = value[0]
            try:
                start_date = datetime.fromisoformat(str(start_str)).date()
                # Shift by delta_months
                new_year = start_date.year + ((start_date.month - 1 + delta_months) // 12)
                new_month = (start_date.month - 1 + delta_months) % 12 + 1
                shifted_start = date(new_year, new_month, 1)

                # Calculate shifted end (next month)
                next_year = shifted_start.year + ((shifted_start.month) // 12)
                next_month = (shifted_start.month) % 12 + 1
                shifted_end = date(next_year, next_month, 1)

                shifted_filters.append({
                    "field": "month",
                    "op": filt.get("op", "between"),
                    "value": [shifted_start.isoformat(), shifted_end.isoformat()]
                })
            except (ValueError, AttributeError):
                shifted_filters.append(filt)
        else:
            shifted_filters.append(filt)

    return shifted_filters


def _build_v2_compare_sql(
    base_cte: str,
    compare_dict: Dict[str, object],
    filters: List[Dict[str, object]],
    group_by: List[str],
    metrics: List[str],
    semantic: SemanticModel,
    order_by: List[Dict[str, str]],
    limit: int,
) -> str:
    """Build SQL for v0.2 compare with baseline and diff_abs/diff_pct.

    Bug fix: Generate proper baseline window with shifted time filter.
    - MoM: shift -1 month
    - YoY: shift -12 months
    - Absolute: use explicit start/end from compare_dict
    """
    baseline = compare_dict.get("baseline")
    method = compare_dict.get("method", "diff_pct")

    # Build current window aggregation
    select_parts = [f"{dimension_expression(dim, semantic, 'base')} AS {dim}" for dim in group_by]
    metric_expr = "COUNT(*) AS value"
    if metrics and metrics[0] in semantic.metrics:
        metric_obj = semantic.metrics[metrics[0]]
        metric_expr = f"{metric_obj.sql_expression()} AS value"

    where_clause = _build_filters(filters, semantic, alias="base")
    group_clause = "GROUP BY " + ", ".join([dimension_expression(dim, semantic, "base") for dim in group_by]) if group_by else ""

    current_sql = f"SELECT {', '.join(select_parts + [metric_expr])} FROM base {where_clause} {group_clause}".strip()

    # Build baseline window with proper time shift
    if baseline == "previous_period":
        # MoM: shift -1 month
        baseline_filters = _shift_month_filter(filters, -1)
    elif baseline == "same_period_last_year":
        # YoY: shift -12 months
        baseline_filters = _shift_month_filter(filters, -12)
    elif baseline == "absolute":
        # Bug fix: Use explicit date ranges for pre/post comparison around pivot
        # Example: "before vs after 2024-06-15" uses exact dates, not month aggregation
        start = compare_dict.get("start")
        end = compare_dict.get("end")
        baseline_filters = [f for f in filters if f.get("field") != "month"]

        # For absolute baseline, use date ranges instead of month boundaries
        # This allows "before vs after 2024-06-15" to work correctly
        if start and end:
            # Build custom date filter (not month-based)
            baseline_filters.append({
                "field": "_date_range",  # Special marker for date filtering
                "op": "between",
                "value": [start, end],
                "_raw_date": True  # Flag to use DATE OCC directly
            })
    else:
        baseline_filters = filters

    baseline_where = _build_filters(baseline_filters, semantic, alias="base")
    baseline_sql = f"SELECT {', '.join(select_parts + [metric_expr])} FROM base {baseline_where} {group_clause}".strip()

    # Join and compute diff
    join_keys = " AND ".join([f"c.{dim} = b.{dim}" for dim in group_by]) if group_by else "1=1"
    diff_expr = "c.value - b.value AS diff_abs" if method == "diff_abs" else "CASE WHEN b.value = 0 THEN NULL ELSE (c.value - b.value) * 100.0 / b.value END AS diff_pct"

    select_cols = ", ".join([f"c.{dim}" for dim in group_by] + ["c.value AS current", "b.value AS baseline", diff_expr])
    final_sql = f"{base_cte}, current AS ({current_sql}), baseline AS ({baseline_sql}) SELECT {select_cols} FROM current c LEFT JOIN baseline b ON {join_keys}"

    if order_by:
        final_sql += f" {_build_order_clause(order_by)}"
    if limit:
        final_sql += f" LIMIT {limit}"

    return final_sql


def _build_v2_topk_within_group_sql(
    base_cte: str,
    top_k_dict: Dict[str, object],
    filters: List[Dict[str, object]],
    group_by: List[str],
    metrics: List[str],
    semantic: SemanticModel,
    limit: int,
) -> str:
    """Build SQL for top-K within each group using ROW_NUMBER().

    Bug fix: Partition by all dimensions EXCEPT the last one (which is ranked).
    Example: "Top 3 crime types within each area"
      - group_by = ["area", "crime_type"]
      - partition by "area", rank "crime_type" by incidents
      - Result: 3 crime_types per area
    """
    k = top_k_dict.get("k", 5)
    rank_by = top_k_dict.get("by", "incidents")

    # Partition by all dimensions except the last (which we're ranking)
    # E.g., group_by=["area", "crime_type"] → partition by "area"
    if len(group_by) > 1:
        partition_dims = group_by[:-1]  # All but last
        partition_clause = "PARTITION BY " + ", ".join(partition_dims)
    else:
        partition_clause = "PARTITION BY 1"  # No partitioning, global top-K

    select_parts = [f"{dimension_expression(dim, semantic, 'base')} AS {dim}" for dim in group_by]

    metric_expr = "COUNT(*) AS incidents"
    if metrics and metrics[0] in semantic.metrics:
        metric_obj = semantic.metrics[metrics[0]]
        metric_expr = f"{metric_obj.sql_expression()} AS {metrics[0]}"

    where_clause = _build_filters(filters, semantic, alias="base")
    group_clause = "GROUP BY " + ", ".join([dimension_expression(dim, semantic, "base") for dim in group_by]) if group_by else ""

    agg_sql = f"SELECT {', '.join(select_parts + [metric_expr])} FROM base {where_clause} {group_clause}".strip()
    ranked_sql = f"SELECT *, ROW_NUMBER() OVER ({partition_clause} ORDER BY {rank_by} DESC) AS rn FROM ({agg_sql}) agg"

    # Select explicit columns (exclude rn from output)
    output_cols = ", ".join(group_by + [rank_by])
    final_sql = f"{base_cte}, ranked AS ({ranked_sql}) SELECT {output_cols} FROM ranked WHERE rn <= {k}"

    if limit:
        final_sql += f" LIMIT {limit}"

    return final_sql


def _build_v2_bucket_sql(
    base_cte: str,
    bucket_dict: Dict[str, object],
    filters: List[Dict[str, object]],
    metrics: List[str],
    semantic: SemanticModel,
    limit: int,
) -> str:
    """Build SQL for bucketing with quantiles."""
    field = bucket_dict.get("field", "incidents")
    method = bucket_dict.get("method", "quantile")
    params = bucket_dict.get("params", {})

    if method == "quantile":
        quantiles = params.get("q", [0, 0.25, 0.5, 0.75, 1])
        # Build percentile_disc for each quantile
        edges_sql = ", ".join([f"PERCENTILE_DISC({q}) WITHIN GROUP (ORDER BY {field}) AS q{int(q*100)}" for q in quantiles])
        edges_cte = f"SELECT {edges_sql} FROM base"

        # Bucket and aggregate (simplified)
        final_sql = f"{base_cte}, edges AS ({edges_cte}) SELECT 'bucket' AS bucket, COUNT(*) AS count FROM base"
    else:
        # Custom edges
        edges = params.get("edges", [])
        final_sql = f"{base_cte} SELECT 'bucket' AS bucket, COUNT(*) AS count FROM base"

    if limit:
        final_sql += f" LIMIT {limit}"

    return final_sql


def _build_v2_aggregate_sql(
    base_cte: str,
    aggregate_dict: Dict[str, object],
    filters: List[Dict[str, object]],
    group_by: List[str],
    semantic: SemanticModel,
    limit: int,
) -> str:
    """Build SQL for median/distinct aggregates.

    Bug fix: For median of incidents, add daily pre-aggregation CTE.
    Example: "Median incidents per day in Hollywood during 2024-03"
      1. Daily pre-agg: GROUP BY day, area → daily incident counts
      2. Median: PERCENTILE_DISC(0.5) of those daily counts by area
    """
    median_of = aggregate_dict.get("median_of")
    distinct_of = aggregate_dict.get("distinct_of")

    select_parts = [f"{dimension_expression(dim, semantic, 'base')} AS {dim}" for dim in group_by]
    agg_exprs = []

    where_clause = _build_filters(filters, semantic, alias="base")

    # Special handling for median of incident counts - requires daily pre-aggregation
    if median_of and median_of.lower() in ("incidents", "count", "events"):
        # Build daily pre-aggregation CTE
        daily_select = ["DATE_TRUNC('day', base.\"DATE OCC\") AS day"]
        daily_select.extend([f"{dimension_expression(dim, semantic, 'base')} AS {dim}" for dim in group_by])
        daily_select.append("COUNT(*) AS incidents")

        daily_group = ["day"]
        daily_group.extend([dimension_expression(dim, semantic, "base") for dim in group_by])

        daily_sql = f"SELECT {', '.join(daily_select)} FROM base {where_clause} GROUP BY {', '.join(daily_group)}"

        # Now compute median of daily incidents, grouped by dimensions (not day)
        median_select = [f"{dim}" for dim in group_by]
        median_select.append("PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY incidents) AS median_incidents")

        median_group = ", ".join(group_by) if group_by else ""
        if median_group:
            final_sql = f"{base_cte}, daily AS ({daily_sql}) SELECT {', '.join(median_select)} FROM daily GROUP BY {median_group}"
        else:
            final_sql = f"{base_cte}, daily AS ({daily_sql}) SELECT {', '.join(median_select)} FROM daily"

        if limit:
            final_sql += f" LIMIT {limit}"

        return final_sql

    # Default path: median of a raw column (like "Vict Age")
    if median_of:
        # Use column name as-is if it contains spaces, otherwise quote it
        col_name = f'"{median_of}"' if ' ' in median_of else median_of
        agg_exprs.append(f"PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY {col_name}) AS median_{median_of.replace(' ', '_')}")

    if distinct_of:
        col_name = f'"{distinct_of}"' if ' ' in distinct_of else distinct_of
        agg_exprs.append(f"COUNT(DISTINCT {col_name}) AS distinct_{distinct_of.replace(' ', '_')}")

    group_clause = "GROUP BY " + ", ".join([dimension_expression(dim, semantic, "base") for dim in group_by]) if group_by else ""

    final_sql = f"{base_cte} SELECT {', '.join(select_parts + agg_exprs)} FROM base {where_clause} {group_clause}".strip()

    if limit:
        final_sql += f" LIMIT {limit}"

    return final_sql


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
