"""Conversation state management, rewriter, and clarifier utilities."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import re
from copy import deepcopy

from .planner import build_plan_rule_based
from .synonyms import detect_weapon_patterns
from .time_utils import extract_time_range
from .nql.model import CompareInternalWindow, CompareSpec, Filter, Metric, NQLQuery
from .patterns import (
    FilterRemoval,
    RangeFilter,
    TopN,
    match_dimension_change,
    match_filter_removal,
    match_filter_addition,
    match_filter_clear,
    match_range_filter,
    match_top_n,
    match_mom_toggle,
    normalize_text,
)


# Dimension canonical names that map to the semantic model.
_DIMENSION_ALIASES = {
    "area": {
        "area",
        "areas",
        "area name",
        "neighborhood",
        "neighborhoods",
    },
    "weapon": {"weapon", "weapons", "weapon type", "weapon types", "weapon category"},
    "crime_type": {
        "crime",
        "crimes",
        "crime type",
        "crime types",
        "offense",
        "offenses",
    },
    "premise": {"premise", "premises", "location type", "location"},
    "vict_age": {"age", "ages", "victim age", "victim ages"},
}

_DIMENSION_TYPES = {
    "area": "category",
    "weapon": "category",
    "crime_type": "category",
    "premise": "category",
    "vict_age": "number",
}


def _normalise_text(value: str) -> str:
    """Deprecated: Use patterns.normalize_text instead."""
    return normalize_text(value)


def _resolve_dimension(candidate: str) -> Optional[str]:
    candidate_norm = _normalise_text(candidate)
    candidate_norm = re.sub(r"[^a-z\s]", "", candidate_norm).strip()
    if not candidate_norm:
        return None
    for canonical, synonyms in _DIMENSION_ALIASES.items():
        if candidate_norm in synonyms or candidate_norm == canonical:
            return canonical
    return None


def _is_self_contained_query(utterance: str) -> bool:
    """Check if utterance is a complete query (not a modification of previous)."""
    lowered = utterance.lower()

    # Check for metric mentions
    metric_keywords = ["incident", "crime", "case", "event", "report", "count", "total", "number"]
    has_metric = any(keyword in lowered for keyword in metric_keywords)

    # Check for time references
    time_keywords = [
        "last year", "this year", "ytd", "year to date",
        "last month", "this month", "last quarter",
        "last 6 months", "last 12 months", "past 6 months",
        "2024", "2025", "q1", "q2", "q3", "q4"
    ]
    has_time = any(keyword in lowered for keyword in time_keywords)

    # Self-contained if it has both metric and time (not just a modification)
    return has_metric and has_time


def _extract_dimension_candidate(utterance: str) -> Optional[str]:
    """Deprecated: Use patterns.match_dimension_change instead."""
    return match_dimension_change(utterance)


def _first_day_of_month(anchor: date) -> date:
    return date(anchor.year, anchor.month, 1)


def _shift_month(anchor: date, delta: int) -> date:
    year = anchor.year + ((anchor.month - 1 + delta) // 12)
    month = (anchor.month - 1 + delta) % 12 + 1
    return date(year, month, 1)


def _previous_month(anchor: date) -> date:
    return _shift_month(anchor, -1)


def _previous_quarter(anchor: date) -> Tuple[date, date]:
    quarter_index = (anchor.month - 1) // 3
    year = anchor.year
    if quarter_index == 0:
        year -= 1
        quarter_index = 3
    else:
        quarter_index -= 1
    start_month = quarter_index * 3 + 1
    start = date(year, start_month, 1)
    end_exclusive = _shift_month(start, 3)
    return start, end_exclusive


def _replace_month_filter(nql: NQLQuery, op: str, value: Any) -> None:
    for filt in nql.filters:
        if filt.field == "month":
            filt.op = op
            filt.value = value
            filt.type = "date"
            return
    nql.filters.insert(0, Filter(field="month", op=op, value=value, type="date"))


def _ensure_trend_group_by(nql: NQLQuery) -> None:
    seen = set(nql.group_by)
    if "month" not in seen:
        nql.group_by.insert(0, "month")


def _set_relative_months_window(
    nql: NQLQuery, n: int, anchor_end: Optional[str]
) -> None:
    window = nql.time.window
    window.type = "relative_months"
    window.n = n
    window.start = None
    window.end = anchor_end
    window.exclusive_end = False
    end_str = anchor_end
    if not end_str:
        # fall back to existing month filter upper bound if present
        for filt in nql.filters:
            if filt.field == "month" and isinstance(filt.value, list) and len(filt.value) == 2:
                end_str = filt.value[1]
                break
    if end_str:
        end_date = date.fromisoformat(end_str)
    else:
        end_date = date.today()
    start_date = _shift_month(end_date, -n)
    _replace_month_filter(nql, "between", [start_date.isoformat(), end_date.isoformat()])


def _set_single_month_window(nql: NQLQuery, start: date) -> None:
    window = nql.time.window
    window.type = "single_month"
    window.start = start.isoformat()
    window.end = None
    window.exclusive_end = False
    window.n = None
    _replace_month_filter(nql, "=", start.isoformat())


def _set_quarter_window(nql: NQLQuery, start: date, end_exclusive: date) -> None:
    window = nql.time.window
    window.type = "quarter"
    window.start = start.isoformat()
    window.end = end_exclusive.isoformat()
    window.exclusive_end = True
    window.n = None
    _replace_month_filter(
        nql,
        "between",
        [start.isoformat(), end_exclusive.isoformat()],
    )


def _toggle_mom_compare(nql: NQLQuery, enabled: bool) -> None:
    if enabled:
        if nql.compare and nql.compare.type == "mom":
            return
        nql.compare = CompareSpec(type="mom", internal_window=CompareInternalWindow())
    else:
        nql.compare = None


def rewrite_followup(
    conversation_state: Dict[str, Any],
    utterance: str,
    *,
    today: Optional[date] = None,
    force_fresh: bool = False,
) -> Dict[str, Any]:
    """Merge a follow-up utterance into the prior NQL conversation state."""

    if not conversation_state:
        raise ValueError("conversation_state cannot be empty for follow-up rewrites")

    today = today or date.today()
    classification = _classify_topic_shift(
        conversation_state, utterance, force_fresh=force_fresh
    )
    if classification["is_fresh_query"]:
        fresh = _build_fresh_query(
            conversation_state,
            utterance,
            today=today,
            reasons=classification["reasons"],
        )
        return fresh.dict()

    working = NQLQuery.parse_obj(deepcopy(conversation_state))
    working.provenance.utterance = utterance

    lowered = utterance.lower()

    candidate_dimension = _extract_dimension_candidate(utterance)
    if candidate_dimension:
        resolved = _resolve_dimension(candidate_dimension)
        if resolved:
            # "same but by X" means REPLACE the dimension, not add to it
            working.dimensions = [resolved]
            # REPLACE group_by with the new dimension (keep month if it was there for trends)
            has_month = "month" in working.group_by
            working.group_by = ["month"] if has_month else []

    # Detect top-N patterns like "top 5", "bottom 3 areas"
    top_n = match_top_n(utterance)
    if top_n:
        # Set limit
        working.limit = top_n.k

        # Update sort to match direction
        if working.metrics:
            metric_field = working.metrics[0].alias
            # Clear existing sort and set new one
            from .nql.model import SortSpec
            working.sort = [SortSpec(by=metric_field, dir=top_n.direction)]

        # If dimension specified, ensure it's in dimensions/group_by
        if top_n.dimension:
            if top_n.dimension not in working.dimensions:
                working.dimensions = [top_n.dimension]
            if top_n.dimension not in working.group_by:
                working.group_by = [top_n.dimension]

    # Detect filter removals like "drop Central", "remove Hollywood and Downtown"
    filter_removal = match_filter_removal(utterance)
    if filter_removal:
        removal_values = [normalize_text(v) for v in filter_removal.values]
        field = working.dimensions[0] if working.dimensions else "area"

        # Try to remove from existing filters
        for filt in working.filters[:]:  # Use slice to allow modification during iteration
            if filt.field == field and filt.field != "month":
                if isinstance(filt.value, list):
                    # Remove values from list (for "in" operator)
                    remaining = [v for v in filt.value if normalize_text(v) not in removal_values]
                    if len(remaining) == 0:
                        # All values removed, delete the filter
                        working.filters.remove(filt)
                    elif len(remaining) != len(filt.value):
                        # Some values removed, update the filter
                        if len(remaining) == 1:
                            filt.op = "="
                            filt.value = remaining[0]
                        else:
                            filt.value = remaining
                elif isinstance(filt.value, str):
                    # Single value filter
                    if normalize_text(filt.value) in removal_values:
                        # Convert to exclusion or remove entirely
                        if filt.op == "=":
                            filt.op = "!="
                        else:
                            working.filters.remove(filt)

    # Detect filter modifications - "include" adds to existing, "only/just" replaces
    filter_addition = match_filter_addition(utterance)
    if filter_addition:
        # Check if this is a time reference before treating as a dimension filter
        value_str = " and ".join(filter_addition.values)
        time_check = extract_time_range(value_str, today=today)

        if not time_check:
            values = filter_addition.values
            field = None
            if working.dimensions:
                field = working.dimensions[0]
            if not field:
                field = "area"
            filt_type = _DIMENSION_TYPES.get(field, "category")

            if filter_addition.is_include:
                # Include: Add to existing filter values
                existing_filter = next((f for f in working.filters if f.field == field and f.field != "month"), None)
                if existing_filter:
                    # Merge with existing values
                    if isinstance(existing_filter.value, list):
                        new_values = list(set(existing_filter.value + values))
                    else:
                        new_values = list(set([existing_filter.value] + values))
                    existing_filter.op = "in"
                    existing_filter.value = new_values
                else:
                    # No existing filter, create new one
                    if len(values) > 1:
                        working.filters.append(Filter(field=field, op="in", value=values, type=filt_type))
                    else:
                        working.filters.append(Filter(field=field, op="=", value=values[0], type=filt_type))
            else:
                # Replace: Remove existing filters and add new one
                working.filters = [f for f in working.filters if f.field != field or f.field == "month"]
                if len(values) > 1:
                    working.filters.append(Filter(field=field, op="in", value=values, type=filt_type))
                else:
                    working.filters.append(Filter(field=field, op="=", value=values[0], type=filt_type))

    # Detect filter clear patterns like "reset filters", "show all areas"
    clear_field = match_filter_clear(utterance)
    if clear_field is not None:
        if clear_field == "":
            # Clear all dimension filters, preserve time filters
            working.filters = [f for f in working.filters if f.field == "month"]
        else:
            # Clear filters for specific field
            working.filters = [f for f in working.filters if f.field != clear_field]

    # Detect range filter patterns like "over 100", "between 50 and 100"
    range_filter = match_range_filter(utterance)
    if range_filter:
        # Determine the metric field from the current query
        # For now, default to "incidents" but could be inferred from working.metrics
        metric_field = range_filter.field
        if working.metrics:
            metric_field = working.metrics[0].alias

        # Add numeric filter
        working.filters.append(
            Filter(
                field=metric_field,
                op=range_filter.op,
                value=range_filter.value,
                type="number"
            )
        )

    # Time adjustments
    anchor_end = working.time.window.end
    time_adjusted = False
    if "last quarter" in lowered:
        start, end_exclusive = _previous_quarter(today)
        _set_quarter_window(working, start, end_exclusive)
        time_adjusted = True
    else:
        match_relative = re.search(r"last\s+(\d{1,2})\s+months", lowered)
        if match_relative:
            n = int(match_relative.group(1))
            _set_relative_months_window(working, n, anchor_end)
            time_adjusted = True
        elif "last 6 months" in lowered:
            _set_relative_months_window(working, 6, anchor_end)
            time_adjusted = True
        elif "last 12 months" in lowered or "last year" in lowered:
            _set_relative_months_window(working, 12, anchor_end)
            time_adjusted = True
        elif "past 6 months" in lowered or "past six months" in lowered:
            _set_relative_months_window(working, 6, anchor_end)
            time_adjusted = True
        elif "last month" in lowered:
            if anchor_end:
                end_date = date.fromisoformat(anchor_end)
            else:
                end_date = today
            start = _previous_month(end_date)
            _set_single_month_window(working, start)
            time_adjusted = True

    if not time_adjusted:
        time_range = extract_time_range(utterance, today=today)
        if time_range:
            if time_range.op == "=":
                _set_single_month_window(working, time_range.start)
            else:
                window = working.time.window
                window.type = "absolute"
                window.start = time_range.start.isoformat()
                window.end = time_range.end.isoformat()
                window.exclusive_end = False
                window.n = None
                _replace_month_filter(
                    working,
                    "between",
                    [
                        time_range.start.isoformat(),
                        time_range.end.isoformat(),
                    ],
                )
            time_adjusted = True

    if "trend" in lowered:
        working.intent = "trend"
        _ensure_trend_group_by(working)

    # MoM toggles
    mom_toggle = match_mom_toggle(utterance)
    if mom_toggle is not None:
        _toggle_mom_compare(working, mom_toggle)

    return working.dict()


@dataclass
class ClarifierResult:
    needs_clarification: bool
    question: Optional[str] = None
    missing_slots: List[str] = field(default_factory=list)
    suggested_answers: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)


def assess_ambiguity(
    conversation_state: Optional[Dict[str, Any]], utterance: str
) -> ClarifierResult:
    """Check whether a follow-up utterance is runnable without clarification."""

    if not conversation_state:
        return ClarifierResult(needs_clarification=False)

    candidate_dimension = _extract_dimension_candidate(utterance)
    if candidate_dimension and not _resolve_dimension(candidate_dimension):
        suggestions = sorted(_DIMENSION_ALIASES.keys())[:4]
        question = "Which dimension should I break that out by?"
        return ClarifierResult(
            needs_clarification=True,
            question=question,
            missing_slots=["dimension"],
            suggested_answers=suggestions,
            context={"dimension_candidate": candidate_dimension},
        )

    return ClarifierResult(needs_clarification=False)


@dataclass
class PendingClarification:
    utterance: str
    question: str
    missing_slots: List[str]
    suggested_answers: List[str]
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationState:
    session_id: str
    last_nql: Optional[Dict[str, Any]] = None
    last_plan: Optional[Dict[str, Any]] = None
    pending: Optional[PendingClarification] = None


class ConversationStore:
    """In-memory registry of conversation state per session."""

    def __init__(self) -> None:
        self._sessions: Dict[str, ConversationState] = {}

    def get(self, session_id: str) -> ConversationState:
        if session_id not in self._sessions:
            self._sessions[session_id] = ConversationState(session_id=session_id)
        return self._sessions[session_id]


    def peek(self, session_id: str) -> Optional[ConversationState]:
        return self._sessions.get(session_id)


    def update_last(self, session_id: str, nql: Dict[str, Any], plan: Dict[str, Any]) -> None:
        state = self.get(session_id)
        state.last_nql = deepcopy(nql)
        state.last_plan = deepcopy(plan)
        state.pending = None

    def set_pending(
        self,
        session_id: str,
        utterance: str,
        question: str,
        missing_slots: List[str],
        suggested_answers: List[str],
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> PendingClarification:
        state = self.get(session_id)
        pending = PendingClarification(
            utterance=utterance,
            question=question,
            missing_slots=missing_slots,
            suggested_answers=suggested_answers,
            context=context or {},
        )
        state.pending = pending
        return pending

    def clear_pending(self, session_id: str) -> None:
        state = self.get(session_id)
        state.pending = None


def apply_clarification_answer(
    conversation_state: Dict[str, Any],
    pending: PendingClarification,
    answer: str,
    *,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Resolve a clarification answer and produce a runnable NQL payload."""

    if not pending.missing_slots:
        raise ValueError("Pending clarification has no missing slots")

    if "dimension" in pending.missing_slots:
        canonical = _resolve_dimension(answer)
        if not canonical:
            candidate = pending.context.get("dimension_candidate")
            canonical = _resolve_dimension(candidate or "") or "area"
        candidate = pending.context.get("dimension_candidate")
        merged = pending.utterance
        if candidate:
            pattern = re.compile(re.escape(candidate), re.IGNORECASE)
            merged = pattern.sub(canonical, merged, count=1)
        else:
            merged = f"{merged} by {canonical}"
        return rewrite_followup(conversation_state, merged, today=today)

    raise ValueError(f"Unsupported clarification slot(s): {pending.missing_slots}")


__all__ = [
    "ConversationState",
    "ConversationStore",
    "PendingClarification",
    "ClarifierResult",
    "assess_ambiguity",
    "apply_clarification_answer",
    "rewrite_followup",
    "_is_self_contained_query",
]

_ANAPHORA_TOKENS = {
    "same",
    "now",
    "also",
    "that",
    "previous",
    "again",
    "include",
    "remove",
}

_QUESTION_STARTERS = (
    "how",
    "what",
    "where",
    "which",
    "who",
    "when",
    "count",
    "do",
    "does",
    "is",
    "are",
)

_COUNT_PREFIXES = (
    "how many",
    "count",
    "what is the total",
)

_METRIC_KEYWORDS = {
    "incident",
    "incidents",
    "crime",
    "crimes",
    "case",
    "cases",
    "event",
    "events",
    "report",
    "reports",
    "total",
    "number",
    "robbery",
    "robberies",
    "stabbing",
    "stabbings",
    "shooting",
    "shootings",
    "assault",
    "assaults",
}

_SUBJECT_VALUE_KEYWORDS = {
    "robbery": ("crime_type", "Robbery"),
    "robberies": ("crime_type", "Robbery"),
    "assault": ("crime_type", "Assault"),
    "assaults": ("crime_type", "Assault"),
    "burglary": ("crime_type", "Burglary"),
    "burglaries": ("crime_type", "Burglary"),
}


def _looks_like_question(text: str) -> bool:
    stripped = text.strip().lower()
    if not stripped:
        return False
    if stripped.endswith("?"):
        return True
    return any(stripped.startswith(prefix) for prefix in _QUESTION_STARTERS)


def _starts_with_count_phrase(text: str) -> Optional[str]:
    for phrase in _COUNT_PREFIXES:
        if text.startswith(phrase):
            return phrase
    return None


def _classify_topic_shift(
    conversation_state: Dict[str, Any],
    utterance: str,
    *,
    force_fresh: bool = False,
) -> Dict[str, Any]:
    lowered = utterance.strip().lower()
    reasons: List[str] = []

    if force_fresh:
        return {"is_fresh_query": True, "reasons": ["forced_context_off"]}

    if not lowered:
        return {"is_fresh_query": False, "reasons": []}

    count_prefix = _starts_with_count_phrase(lowered)
    if count_prefix:
        reasons.append(f"starts_with_{count_prefix.replace(' ', '_')}")

    looks_like_question = _looks_like_question(lowered)
    contains_anaphora = any(token in lowered for token in _ANAPHORA_TOKENS)
    has_metric_keyword = any(keyword in lowered for keyword in _METRIC_KEYWORDS)
    if looks_like_question and not contains_anaphora and has_metric_keyword:
        reasons.append("question_no_anaphora")

    if looks_like_question and " by " not in lowered:
        if re.search(r"\b(?:in|for|at|within|across)\s+[a-z]", lowered):
            reasons.append("new_entity_preposition")

    return {"is_fresh_query": bool(reasons), "reasons": reasons}


def _infer_subject_filters(
    utterance: str,
    existing_fields: List[str],
) -> List[Filter]:
    lowered = utterance.lower()
    filters: List[Filter] = []
    seen_fields = set(existing_fields)

    for keyword, (field, value) in _SUBJECT_VALUE_KEYWORDS.items():
        if re.search(rf"\b{re.escape(keyword)}\b", lowered) and field not in seen_fields:
            filters.append(
                Filter(
                    field=field,
                    op="=",
                    value=value,
                    type=_DIMENSION_TYPES.get(field, "category"),
                )
            )
            seen_fields.add(field)

    weapon_patterns = detect_weapon_patterns(utterance)
    if weapon_patterns and "weapon" not in seen_fields:
        normalised = [pattern.lower() for pattern in weapon_patterns]
        filters.append(
            Filter(field="weapon", op="like_any", value=normalised, type="text_raw")
        )
        seen_fields.add("weapon")

    return filters


def _reset_time_for_fresh_query(
    nql: NQLQuery,
    *,
    utterance: str,
    conversation_state: Dict[str, Any],
    today: Optional[date],
) -> None:
    anchor_end = (
        conversation_state.get("time", {})
        .get("window", {})
        .get("end")
    )

    time_range = extract_time_range(utterance, today=today)
    if time_range:
        if time_range.op == "=":
            _set_single_month_window(nql, time_range.start)
        else:
            window = nql.time.window
            window.type = "absolute"
            window.start = time_range.start.isoformat()
            window.end = time_range.end.isoformat()
            window.exclusive_end = False
            window.n = None
            _replace_month_filter(
                nql,
                "between",
                [time_range.start.isoformat(), time_range.end.isoformat()],
            )
        return

    if not anchor_end and today:
        anchor_end = date(today.year, today.month, 1).isoformat()

    _set_relative_months_window(nql, 12, anchor_end)


def _build_filters_from_plan(plan_filters: List[Dict[str, Any]]) -> List[Filter]:
    built: List[Filter] = []
    for entry in plan_filters:
        field = entry.get("field")
        if not field or field == "month":
            continue
        op = entry.get("op", "=")
        value = entry.get("value")
        if field == "weapon" and op in {"like", "ilike", "like_any"}:
            if isinstance(value, list):
                normalised_value = [str(item).lower() for item in value]
            else:
                normalised_value = str(value).lower()
            built.append(
                Filter(
                    field="weapon",
                    op=op,
                    value=normalised_value,
                    type="text_raw",
                )
            )
            continue
        filt_type = _DIMENSION_TYPES.get(field, "category")
        built.append(Filter(field=field, op=op, value=value, type=filt_type))
    return built


def _build_fresh_query(
    conversation_state: Dict[str, Any],
    utterance: str,
    *,
    today: Optional[date],
    reasons: List[str],
) -> NQLQuery:
    base = NQLQuery.parse_obj(deepcopy(conversation_state))
    base.intent = "aggregate"
    base.dimensions = []
    base.group_by = []
    base.compare = None
    base.sort = []
    base.filters = []
    if base.flags:
        base.flags.trend = None

    plan = build_plan_rule_based(utterance)
    group_by = [dim for dim in plan.get("group_by", []) if isinstance(dim, str)]
    includes_grouping = bool(group_by)
    if includes_grouping:
        base.group_by = [dim for dim in group_by if dim != "month"]

    count_prefix = _starts_with_count_phrase(utterance.lower().strip())
    if count_prefix:
        base.metrics = [Metric(name="incident_count", agg="count", alias="count")]
    else:
        base.metrics = [metric.copy(deep=True) for metric in base.metrics]

    _reset_time_for_fresh_query(
        base,
        utterance=utterance,
        conversation_state=conversation_state,
        today=today,
    )

    filters_from_plan = _build_filters_from_plan(plan.get("filters", []))
    existing_fields = [f.field for f in filters_from_plan]
    subject_filters = _infer_subject_filters(utterance, existing_fields)
    base.filters.extend(filters_from_plan)
    for filt in subject_filters:
        if filt.field not in {f.field for f in base.filters if f.field != "month"}:
            base.filters.append(filt)

    base.provenance.retrieval_notes = []
    reason_slug = "+".join(reasons) if reasons else "manual"
    note = f"topic_shift:{reason_slug}"
    if count_prefix and " by " not in utterance.lower():
        note = f"{note} -> reset dims/group_by"
    base.provenance.retrieval_notes.append(note)

    base.provenance.utterance = utterance
    return base
