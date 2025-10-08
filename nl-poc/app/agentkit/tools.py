"""Utility tools exposed to the AgentKit layer.

The tools deliberately wrap the existing deterministic NQL pipeline so that the
OpenAI Agent can orchestrate conversations without bypassing the carefully
curated execution path. Each tool returns plain JSON-serialisable structures and
keeps the behaviour of the legacy ``/ask`` and ``/chat`` routes intact.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, Field

from ..planner import build_plan, get_last_intent_engine
from ..summarizer import HallucinationError, SummarizerError, summarize_results
from ..viz import build_narrative, choose_chart


class QueryCompilationResult(BaseModel):
    """Structured representation returned by ``compile_plan_and_query``."""

    question: str = Field(..., description="Natural language question supplied by the user.")
    plan: Dict[str, Any] = Field(..., description="Resolved analytics plan ready for SQL compilation.")
    sql: str = Field(..., description="Deterministic SELECT query executed against DuckDB.")
    table: List[Dict[str, Any]] = Field(..., description="Tabular result rows returned by DuckDB.")
    chart: Dict[str, Any] = Field(..., description="Chart recommendation derived from the semantic plan.")
    summary: str = Field(..., description="Single sentence summary describing the key insight.")
    warnings: List[str] = Field(default_factory=list, description="Non fatal warnings produced by guardrails.")


class SummaryResult(BaseModel):
    """Response envelope for ``summarize_and_validate`` outputs."""

    summary: str = Field(..., description="Narrative explanation of the result set.")
    chart: Dict[str, Any] = Field(..., description="Renderable chart specification.")
    warnings: List[str] = Field(default_factory=list, description="Additional warning messages emitted by guardrails.")


def _get_main_module():
    """Import ``app.main`` lazily to avoid circular import issues."""

    from .. import main as main_app  # Local import keeps module import order intact.

    return main_app


def _ensure_runtime_dependencies(main_app: Any) -> None:
    """Validate that the FastAPI application has initialised its shared state."""

    missing: List[str] = []
    for key in ("executor", "resolver", "semantic"):
        if key not in main_app._state:  # type: ignore[attr-defined]
            missing.append(key)
    if missing:
        raise RuntimeError(
            "Application state has not been initialised; missing: " + ", ".join(sorted(missing))
        )


def _execute_with_legacy_pipeline(plan: Dict[str, Any], question: str, *, intent_engine: str) -> Dict[str, Any]:
    """Proxy to the existing execution helper defined in ``app.main``."""

    main_app = _get_main_module()
    _ensure_runtime_dependencies(main_app)
    return main_app._execute_query(plan, question, intent_engine=intent_engine)  # type: ignore[attr-defined]


def compile_plan_and_query(
    *,
    question: str,
    prefer_llm: Optional[bool] = None,
) -> QueryCompilationResult:
    """Convert natural language into deterministic analytics output.

    The function mirrors the behaviour of ``/ask`` while returning a compact
    response envelope that the AgentKit runtime can reason about.  All heavy
    lifting is delegated to the existing planner/SQL builder so no additional
    logic is duplicated.
    """

    cleaned_question = (question or "").strip()
    if not cleaned_question:
        raise ValueError("Question must be a non-empty string.")

    plan = build_plan(cleaned_question, prefer_llm=prefer_llm)
    intent_engine = get_last_intent_engine()
    execution = _execute_with_legacy_pipeline(plan, cleaned_question, intent_engine=intent_engine)

    result = QueryCompilationResult(
        question=cleaned_question,
        plan=execution.get("plan", {}),
        sql=execution.get("sql", ""),
        table=execution.get("table", []),
        chart=execution.get("chart", {}),
        summary=execution.get("answer", ""),
        warnings=list(execution.get("warnings", []) or []),
    )
    return result


def summarize_and_validate(
    *,
    plan: Dict[str, Any],
    records: Iterable[Dict[str, Any]],
    sql: str = "",
) -> SummaryResult:
    """Produce a narrative summary while surfacing validation warnings.

    ``records`` may be any iterable of dictionaries; it is eagerly materialised
    to ensure deterministic iteration order for JSON serialisation.
    """

    materialised_records = [dict(row) for row in records]

    chart = choose_chart(plan, materialised_records)
    narrative = build_narrative(plan, materialised_records)
    warnings: List[str] = []

    use_summarizer = os.getenv("USE_SUMMARIZER", "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }

    if use_summarizer:
        try:
            summary_blob = summarize_results(materialised_records, plan)
        except (SummarizerError, HallucinationError):
            # Fall back to deterministic narrative on summariser failures.  The
            # legacy guardrails expect a warning to be propagated back to the user.
            warnings.append("llm_summarizer_unavailable")
            summary_text = narrative
        else:
            summary_text = summary_blob.get("explanation") or narrative
            extra_warnings = summary_blob.get("warnings")
            if isinstance(extra_warnings, list):
                warnings.extend(str(w) for w in extra_warnings if w)
    else:
        summary_text = narrative

    payload = SummaryResult(summary=summary_text, chart=chart, warnings=warnings)
    return payload


__all__ = ["compile_plan_and_query", "summarize_and_validate", "QueryCompilationResult", "SummaryResult"]

# --- Agent-facing tool: TrueSight query --------------------------------------

from typing import Optional, Dict, Any

def truesight_query(*, utterance: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    AgentBuilder tool entrypoint.
    Runs the deterministic NQL pipeline and returns renderable results.

    Parameters
    ----------
    utterance : str
        The user's natural-language analytics question.
    session_id : Optional[str]
        Optional thread/session identifier (you can pass ChatKit thread_id).

    Returns
    -------
    dict
        {
          "status": "complete",
          "answer": str,
          "table": List[Dict[str, Any]],
          "chart": Dict[str, Any],
          "sql": str,
          "warnings": List[str],
          "session_id": Optional[str]
        }
    """
    try:
        result = compile_plan_and_query(question=utterance)
        return {
            "status": "complete",
            "answer": result.summary,
            "table": result.table,
            "chart": result.chart,
            "sql": result.sql,
            "warnings": result.warnings,
            "session_id": session_id,
        }
    except Exception as e:
        # Keep error payload simple + serialisable for the Agent runtime
        return {
            "status": "error",
            "detail": str(e),
            "session_id": session_id,
        }
