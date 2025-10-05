"""Validator for NQL v0.1 payloads."""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, List, Optional, Set

from .model import NQLQuery


SERVER_MAX_LIMIT = 2000


class NQLValidationError(ValueError):
    """Raised when an NQL payload fails critic validation."""


def _parse_date(raw: Optional[str], context: str) -> date:
    if not raw:
        raise NQLValidationError(f"{context} must be provided")
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError as exc:  # pragma: no cover - defensive
        raise NQLValidationError(f"{context} must be an ISO date: {raw}") from exc


def _first_day_of_month(dt: date) -> date:
    return date(dt.year, dt.month, 1)


def _next_month(dt: date) -> date:
    if dt.month == 12:
        return date(dt.year + 1, 1, 1)
    return date(dt.year, dt.month + 1, 1)


def _next_quarter_start(dt: date) -> date:
    quarter = (dt.month - 1) // 3
    next_quarter = (quarter + 1) % 4
    year = dt.year + (1 if quarter == 3 else 0)
    month = next_quarter * 3 + 1
    return date(year, month, 1)


def _ensure_quarter_bounds(nql: NQLQuery, critic_pass: List[str]) -> None:
    if nql.time.window.type != "quarter" or not nql.flags.quarter_exclusive_end:
        return
    start = _parse_date(nql.time.window.start, "quarter.start")
    end = _parse_date(nql.time.window.end, "quarter.end")
    expected = _next_quarter_start(start)
    if end != expected:
        raise NQLValidationError("quarter window end must be first day of next quarter")
    if not nql.time.window.exclusive_end:
        nql.time.window.exclusive_end = True
    critic_pass.append("quarter_exclusive_end")


def _ensure_trend_grouping(nql: NQLQuery, critic_pass: List[str]) -> None:
    if nql.intent != "trend" or not nql.flags.require_grouping_for_trend:
        return
    time_dim = "month"
    present = set(nql.group_by) | set(nql.dimensions)
    if time_dim not in present:
        nql.group_by.insert(0, time_dim)
    if nql.time.window.type == "relative_months" and nql.time.window.n is None:
        nql.time.window.n = 12
    critic_pass.append("trend_grouping")


def _ensure_mom_expand_prior(nql: NQLQuery, critic_pass: List[str]) -> None:
    compare = nql.compare
    if not compare or compare.type != "mom" or nql.time.window.type != "single_month":
        return
    if compare.internal_window is None:
        from .model import CompareInternalWindow

        compare.internal_window = CompareInternalWindow(expand_prior=True)
    else:
        compare.internal_window.expand_prior = True
    critic_pass.append("mom_single_month_expand_prior")


def _validate_like_filters(nql: NQLQuery, critic_pass: List[str]) -> None:
    pattern_ops = {"like", "ilike", "like_any"}
    for filt in nql.filters:
        if filt.op not in pattern_ops:
            continue
        if filt.type != "text_raw":
            raise NQLValidationError("LIKE filters must use type=text_raw for passthrough")
    critic_pass.append("like_passthrough")


def _validate_sort(nql: NQLQuery, critic_pass: List[str]) -> None:
    if not nql.sort:
        return
    metric_aliases = {metric.alias for metric in nql.metrics}
    dimension_names: Set[str] = set(nql.dimensions) | set(nql.group_by)
    dimension_names.add("month")
    for sort in nql.sort:
        if sort.by not in metric_aliases and sort.by not in dimension_names:
            raise NQLValidationError(f"Sort target '{sort.by}' must be a metric alias or dimension")
    critic_pass.append("sort_safety")


def _clamp_limit(nql: NQLQuery, critic_pass: List[str]) -> None:
    rowcap_hint = min(max(1, nql.flags.rowcap_hint), SERVER_MAX_LIMIT)
    nql.flags.rowcap_hint = rowcap_hint
    nql.limit = min(max(1, nql.limit), rowcap_hint, SERVER_MAX_LIMIT)
    critic_pass.append("limit_clamp")


def validate_nql(nql: NQLQuery) -> NQLQuery:
    """Run critic validations and return a possibly-normalised copy."""

    working = nql.copy(deep=True)
    if not working.metrics:
        raise NQLValidationError("metrics must contain at least one entry")
    critic_pass: List[str] = []

    _ensure_quarter_bounds(working, critic_pass)
    _ensure_trend_grouping(working, critic_pass)
    _ensure_mom_expand_prior(working, critic_pass)
    _validate_like_filters(working, critic_pass)
    _validate_sort(working, critic_pass)
    _clamp_limit(working, critic_pass)

    provenance = working.provenance
    seen: Iterable[str] = provenance.critic_pass
    merged = list(dict.fromkeys([*seen, *critic_pass]))
    working.provenance.critic_pass = merged
    return working
