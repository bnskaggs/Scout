"""Conversation state management, rewriter, and clarifier utilities."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import re
from copy import deepcopy

from .nql.model import CompareInternalWindow, CompareSpec, Filter, NQLQuery


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
    return re.sub(r"\s+", " ", value.strip().lower())


def _resolve_dimension(candidate: str) -> Optional[str]:
    candidate_norm = _normalise_text(candidate)
    candidate_norm = re.sub(r"[^a-z\s]", "", candidate_norm).strip()
    if not candidate_norm:
        return None
    for canonical, synonyms in _DIMENSION_ALIASES.items():
        if candidate_norm in synonyms or candidate_norm == canonical:
            return canonical
    return None


def _extract_dimension_candidate(utterance: str) -> Optional[str]:
    """Pull a possible dimension target from the utterance."""

    lowered = utterance.lower()
    patterns = [
        r"same(?:\s+view)?\s+but\s+by\s+([a-z\s]+)",
        r"by\s+([a-z\s]+)",
        r"break(?:ing|)\s+down\s+by\s+([a-z\s]+)",
        r"group\s+by\s+([a-z\s]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            candidate = match.group(1).strip()
            candidate = re.sub(r"\bfor\b", "", candidate).strip()
            return candidate
    return None


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
    conversation_state: Dict[str, Any], utterance: str, *, today: Optional[date] = None
) -> Dict[str, Any]:
    """Merge a follow-up utterance into the prior NQL conversation state."""

    if not conversation_state:
        raise ValueError("conversation_state cannot be empty for follow-up rewrites")

    today = today or date.today()
    working = NQLQuery.parse_obj(deepcopy(conversation_state))
    working.provenance.utterance = utterance

    lowered = utterance.lower()

    candidate_dimension = _extract_dimension_candidate(utterance)
    if candidate_dimension:
        resolved = _resolve_dimension(candidate_dimension)
        if resolved:
            working.dimensions = [resolved]
            # Remove duplicate entry if already present in group_by
            working.group_by = [dim for dim in working.group_by if dim != resolved]

    # Detect filter removals like "filter out Central"
    remove_match = re.search(
        r"(?:filter out|exclude|remove)\s+([\w\s'&/-]+)", lowered
    )
    if remove_match:
        value = remove_match.group(1).strip().strip(". ")
        value_norm = _normalise_text(value)
        for filt in working.filters:
            if isinstance(filt.value, str) and _normalise_text(str(filt.value)) == value_norm:
                if filt.op == "=":
                    filt.op = "!="
                else:
                    working.filters = [f for f in working.filters if f is not filt]
                break

    # Detect filter additions like "only Central" or "just show Hollywood"
    add_match = re.search(r"(?:only|just)\s+([\w\s'&/-]+)", lowered)
    if add_match:
        value = add_match.group(1).strip().strip(". ")
        field = None
        if working.dimensions:
            field = working.dimensions[0]
        if not field:
            # fall back to area if unsure
            field = "area"
        filt_type = _DIMENSION_TYPES.get(field, "category")
        working.filters = [
            f for f in working.filters if f.field != field or f.field == "month"
        ]
        working.filters.append(
            Filter(field=field, op="=", value=value.title(), type=filt_type)
        )

    # Time adjustments
    if "last quarter" in lowered:
        start, end_exclusive = _previous_quarter(today)
        _set_quarter_window(working, start, end_exclusive)
    else:
        match_relative = re.search(r"last\s+(\d{1,2})\s+months", lowered)
        if match_relative:
            n = int(match_relative.group(1))
            anchor_end = working.time.window.end
            _set_relative_months_window(working, n, anchor_end)
        elif "last 6 months" in lowered:
            anchor_end = working.time.window.end
            _set_relative_months_window(working, 6, anchor_end)
        elif "last 12 months" in lowered or "last year" in lowered:
            anchor_end = working.time.window.end
            _set_relative_months_window(working, 12, anchor_end)
        elif "past 6 months" in lowered or "past six months" in lowered:
            anchor_end = working.time.window.end
            _set_relative_months_window(working, 6, anchor_end)
        elif "last month" in lowered:
            anchor_end = working.time.window.end
            if anchor_end:
                end_date = date.fromisoformat(anchor_end)
            else:
                end_date = today
            start = _previous_month(end_date)
            _set_single_month_window(working, start)

    if "trend" in lowered:
        working.intent = "trend"
        _ensure_trend_group_by(working)

    # MoM toggles
    if re.search(r"(turn on|add|include).*(mom|month over month)", lowered):
        _toggle_mom_compare(working, True)
    elif re.search(r"(turn off|remove|drop).*(mom|month over month)", lowered):
        _toggle_mom_compare(working, False)
    elif re.search(r"\bmom\b", lowered) and "turn off" not in lowered:
        _toggle_mom_compare(working, True)

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
]

