"""Plan resolver and validator against the semantic configuration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from .executor import DuckDBExecutor
from .time_utils import TimeRange, describe_time_range


@dataclass
class SemanticDimension:
    name: str
    column: str
    dtype: str = "text"
    bucket: Optional[str] = None

    def sql_expression(self) -> str:
        if self.name == "month":
            return "DATE_TRUNC('month', \"DATE OCC\")"
        if " " in self.column:
            return f'"{self.column}"'
        return f'"{self.column}"'


@dataclass
class SemanticMetric:
    name: str
    agg: str
    grain: List[str]

    def sql_expression(self) -> str:
        if self.agg == "count":
            return "COUNT(*)"
        raise ValueError(f"Unsupported metric aggregation: {self.agg}")


@dataclass
class SemanticModel:
    table: str
    date_grain: str
    dimensions: Dict[str, SemanticDimension]
    metrics: Dict[str, SemanticMetric]

    @classmethod
    def from_yaml(cls, path: Path) -> "SemanticModel":
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        defaults = data.get("defaults", {})
        table = defaults.get("table")
        date_grain = defaults.get("date_grain", "month")
        dimensions: Dict[str, SemanticDimension] = {}
        for name, payload in data.get("dimensions", {}).items():
            dimensions[name] = SemanticDimension(
                name=name,
                column=payload.get("column", name),
                dtype=payload.get("type", "text"),
                bucket=payload.get("bucket"),
            )
        metrics: Dict[str, SemanticMetric] = {}
        for name, payload in data.get("metrics", {}).items():
            metrics[name] = SemanticMetric(
                name=name,
                agg=payload.get("agg", "count"),
                grain=payload.get("grain", []),
            )
        return cls(table=table, date_grain=date_grain, dimensions=dimensions, metrics=metrics)


class PlanResolutionError(Exception):
    def __init__(self, message: str, suggestions: Optional[List[str]] = None):
        super().__init__(message)
        self.suggestions = suggestions or []


class PlanResolver:
    _PATTERN_OPERATORS = {"like", "not like", "like_any", "contains"}

    def __init__(self, semantic: SemanticModel, executor: DuckDBExecutor):
        self.semantic = semantic
        self.executor = executor

    @staticmethod
    def _shift_month(anchor: date, delta: int) -> date:
        year = anchor.year + ((anchor.month - 1 + delta) // 12)
        month = (anchor.month - 1 + delta) % 12 + 1
        return date(year, month, 1)

    def _should_bypass_value_resolution(self, op: Optional[str]) -> bool:
        if not op:
            return False
        return op.lower() in self._PATTERN_OPERATORS

    def _validate_metric(self, metric: str) -> None:
        if metric not in self.semantic.metrics:
            raise PlanResolutionError(f"Unknown metric '{metric}'")

    def _validate_dimension(self, dimension: str) -> None:
        if dimension not in self.semantic.dimensions:
            raise PlanResolutionError(f"Unknown dimension '{dimension}'")

    def _resolve_filter_values(self, field: str, op: str, value):
        if field == "month":
            return value
        dimension = self.semantic.dimensions.get(field)
        if not dimension:
            return value
        if isinstance(value, list):
            values = value
        else:
            values = [value]
        resolved_values = []
        for item in values:
            resolved = self.executor.find_closest_value(dimension, item)
            if not resolved:
                suggestions = self.executor.closest_matches(dimension, item)
                raise PlanResolutionError(
                    f"Could not find value '{item}' for {field}", suggestions=suggestions
                )
            resolved_values.append(resolved)
        return resolved_values if isinstance(value, list) else resolved_values[0]

    def resolve(self, plan: Dict[str, object]) -> Dict[str, object]:
        for metric in plan.get("metrics", []):
            self._validate_metric(metric)
        for dimension in plan.get("group_by", []):
            self._validate_dimension(dimension)
        filters: List[Dict[str, object]] = []
        time_range: Optional[TimeRange] = None
        for filter_ in plan.get("filters", []):
            field = filter_["field"]
            if field == "month":
                value = filter_.get("value")
                op = filter_.get("op", "between")
                if op == "between" and isinstance(value, list):
                    start = value[0] if value else None
                    end = value[1] if len(value) > 1 else None
                    if start and (end is None or end == start):
                        filter_ = {"field": field, "op": "=", "value": start}
                        value = start
                if isinstance(value, (list, tuple)):
                    start = value[0]
                    end = value[1] if len(value) > 1 else None
                    filters.append({"field": field, "op": filter_["op"], "value": [start, end]})
                else:
                    filters.append(filter_)
                start = value[0] if isinstance(value, list) else value
                end = value[1] if isinstance(value, list) and len(value) > 1 else None
                if start:
                    start_date = start
                    end_date = end or start
                    time_range = TimeRange(
                        start=self.executor.parse_date(start_date),
                        end=self.executor.parse_date(end_date),
                        label="",
                    )
            else:
                op = filter_.get("op")
                if self._should_bypass_value_resolution(op):
                    resolved_value = filter_.get("value")
                else:
                    resolved_value = self._resolve_filter_values(field, op, filter_["value"])
                filters.append({"field": field, "op": filter_["op"], "value": resolved_value})
        order_by = plan.get("order_by")
        if order_by is None:
            order_by = [{"field": "incidents", "dir": "desc"}]
        limit_value = plan.get("limit")
        if limit_value in (None, "", 0, "0"):
            limit = 0
        else:
            limit = min(int(limit_value), 2000)
        compare = plan.get("compare")
        resolved_plan = {
            "metrics": plan.get("metrics", []),
            "group_by": plan.get("group_by", []),
            "filters": filters,
            "order_by": order_by,
            "limit": limit,
        }
        if compare:
            resolved_plan["compare"] = compare
            if compare.get("type") == "mom" and time_range and time_range.start == time_range.end:
                month_filters = [f for f in filters if f.get("field") == "month"]
                if month_filters:
                    target_start = time_range.start
                    start = self._shift_month(target_start, -1)
                    end = self._shift_month(target_start, 1)
                    resolved_plan["internal_window"] = {
                        "field": "month",
                        "op": "between",
                        "value": [start.isoformat(), end.isoformat()],
                    }
        resolved_plan["time_window_label"] = describe_time_range(time_range)
        return resolved_plan


def load_semantic_model(path: Path) -> SemanticModel:
    return SemanticModel.from_yaml(path)
