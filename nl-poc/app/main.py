"""FastAPI entrypoint for the NL analytics proof-of-concept."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import guardrails, sql_builder, viz
from .conversation import (
    ConversationStore,
    assess_ambiguity,
    apply_clarification_answer,
    rewrite_followup,
)
from .executor import DuckDBExecutor
from .nql import NQLValidationError, compile_payload
from .planner import build_plan, get_last_intent_engine
from .resolver import PlanResolutionError, PlanResolver, load_semantic_model

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
CONFIG_DIR = BASE_DIR / "config"
DB_PATH = DATA_DIR / "games.duckdb"
SEMANTIC_PATH = CONFIG_DIR / "semantic.yml"


class AskRequest(BaseModel):
    question: str
    use_llm: Optional[bool] = None


class ChatCompleteRequest(BaseModel):
    session_id: str
    utterance: str
    use_llm: Optional[bool] = None


class ChatClarifyRequest(BaseModel):
    session_id: str
    answer: str


import logging, sys

llm_logger = logging.getLogger("app.llm_client")
llm_logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

llm_logger.handlers.clear()        # avoid duplicate logs if reloading
llm_logger.addHandler(handler)
llm_logger.propagate = False       # don't let Uvicorn re-handle it

app = FastAPI(title="Scout NL Analytics POC")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

_state: Dict[str, Any] = {
    "last_debug": None,
    "source_csv": None,
}

_conversations = ConversationStore()


def _quote(identifier: str) -> str:
    if identifier.startswith('"') and identifier.endswith('"'):
        return identifier
    return f'"{identifier}"'


def _normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _build_view_from_csv(conn: duckdb.DuckDBPyConnection, csv_path: Path) -> None:
    rel = duckdb.read_csv(str(csv_path))
    columns = rel.columns
    expected = [
        "DATE OCC",
        "AREA NAME",
        "Crm Cd Desc",
        "Premis Desc",
        "Weapon Desc",
        "DR_NO",
        "Vict Age",
    ]
    actual_lookup = {_normalise(col): col for col in columns}
    select_exprs: List[str] = []
    consumed: set[str] = set()
    for col in expected:
        normalised = _normalise(col)
        source_col = actual_lookup.get(normalised)
        if source_col:
            select_exprs.append(f"{_quote(source_col)} AS {_quote(col)}")
            consumed.add(source_col)
        else:
            select_exprs.append(f"NULL AS {_quote(col)}")
    # include all other columns as-is
    for col in columns:
        if col not in consumed:
            select_exprs.append(f"{_quote(col)}")
    conn.execute("CREATE OR REPLACE TABLE la_crime_source AS SELECT * FROM read_csv_auto(?)", [str(csv_path)])
    select_clause = ", ".join(select_exprs)
    conn.execute(f"CREATE OR REPLACE VIEW la_crime_raw AS SELECT {select_clause} FROM la_crime_source")
    conn.execute(
        "CREATE OR REPLACE VIEW la_crime_month_view AS "
        "SELECT DATE_TRUNC('month', \"DATE OCC\") AS month, * FROM la_crime_raw"
    )


def _ensure_database() -> DuckDBExecutor:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SEMANTIC_PATH.exists():
        raise RuntimeError("semantic.yml missing; ensure configuration is present.")
    csv_files = sorted(DATA_DIR.glob("*.csv"))
    if not csv_files:
        raise RuntimeError("Place a CSV file in ./data before starting the service.")
    csv_path = csv_files[0]
    _state["source_csv"] = csv_path.name
    conn = duckdb.connect(str(DB_PATH))
    _build_view_from_csv(conn, csv_path)
    conn.close()
    return DuckDBExecutor(DB_PATH)


@app.on_event("startup")
def startup_event() -> None:
    executor = _ensure_database()
    semantic = load_semantic_model(SEMANTIC_PATH)
    _state["executor"] = executor
    _state["semantic"] = semantic
    _state["resolver"] = PlanResolver(semantic, executor)


@app.on_event("shutdown")
def shutdown_event() -> None:
    executor: DuckDBExecutor = _state.get("executor")
    if executor:
        executor.close()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


def _summarise_filters(filters: List[Dict[str, Any]]) -> List[str]:
    descriptions = []
    for filt in filters:
        field = filt.get("field")
        op = filt.get("op")
        value = filt.get("value")
        descriptions.append(f"{field} {op} {value}")
    return descriptions


def _apply_small_n(plan: Dict[str, Any], records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if "vict_age" not in plan.get("group_by", []):
        return records
    protected_metric = plan.get("metrics", ["incidents"])[0]
    threshold = 5
    kept: List[Dict[str, Any]] = []
    suppressed_total = 0
    other_row: Dict[str, Any] = {"vict_age": "Other (<5)"}
    for row in records:
        value = row.get(protected_metric)
        if value is None or value >= threshold:
            kept.append(row)
        else:
            suppressed_total += value
            for key, val in row.items():
                if key not in ("vict_age", protected_metric) and isinstance(val, (int, float)):
                    other_row.setdefault(key, None)
    if suppressed_total:
        other_row[protected_metric] = suppressed_total
        kept.append(other_row)
    return kept


def _format_change_pct(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Format change_pct values as percentage strings with 2 decimals.

    Keeps raw change_pct for calculations, adds change_pct_formatted for display.
    """
    if not records or "change_pct" not in records[0]:
        return records

    formatted_records = []
    for row in records:
        row_copy = row.copy()
        change_pct = row_copy.get("change_pct")
        if change_pct is not None:
            # SQL already multiplied by 100, just format with 2 decimals
            pct_value = round(change_pct, 2)
            row_copy["change_pct_formatted"] = f"{pct_value:+.2f}%"
        else:
            row_copy["change_pct_formatted"] = "N/A"
        formatted_records.append(row_copy)

    return formatted_records


def _execute_query(plan: Dict[str, Any], utterance: str, *, intent_engine: str) -> Dict[str, Any]:
    executor: DuckDBExecutor = _state["executor"]
    resolver: PlanResolver = _state["resolver"]
    semantic = _state["semantic"]

    try:
        resolved_plan = resolver.resolve(plan)
    except PlanResolutionError as exc:
        raise HTTPException(
            status_code=400,
            detail={"message": str(exc), "suggestions": exc.suggestions},
        ) from exc

    sql = sql_builder.build(resolved_plan, semantic)
    try:
        guardrails.enforce(sql, resolved_plan)
    except guardrails.GuardrailError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = executor.query(sql)
    records = _apply_small_n(resolved_plan, result.records)
    records = _format_change_pct(records)
    chart = viz.choose_chart(resolved_plan, records)
    narrative = viz.build_narrative(resolved_plan, records)

    plan_metadata = {
        "utterance": utterance,
        "nql": plan.get("_nql"),
        "critic_pass": plan.get("_critic_pass", []),
        "engine": intent_engine,
        "runtime_ms": result.runtime_ms,
        "rowcount": result.rowcount,
    }
    llm_logger.info("telemetry=%s", json.dumps(plan_metadata, default=str))

    warnings: List[str] = []
    rowcap_warning = guardrails.check_rowcap_exceeded(result.truncated)
    if rowcap_warning:
        warnings.append(rowcap_warning)

    metric_defs = {
        metric: semantic.metrics[metric].sql_expression()
        for metric in resolved_plan.get("metrics", [])
    }

    response = {
        "answer": narrative,
        "table": records,
        "chart": chart,
        "sql": sql,
        "plan": resolved_plan,
        "engine": intent_engine,
        "runtime_ms": result.runtime_ms,
        "rowcount": result.rowcount,
        "warnings": warnings,
        "lineage": {
            "metric_defs": metric_defs,
            "time_window": resolved_plan.get("time_window_label", "All time"),
            "filters": _summarise_filters(resolved_plan.get("filters", [])),
            "source": _state.get("source_csv"),
            "runtime_ms": result.runtime_ms,
        },
        "nql": plan.get("_nql"),
    }

    _state["last_debug"] = {
        "plan": resolved_plan,
        "sql": sql,
        "runtime_ms": result.runtime_ms,
        "rowcount": result.rowcount,
    }
    return response


def _describe_time_window(window: Optional[Dict[str, Any]]) -> Optional[str]:
    if not window:
        return None
    window_type = window.get("type")
    if window_type == "relative_months":
        months = window.get("n") or 12
        return f"Last {months} months"
    if window_type == "quarter":
        start = window.get("start")
        end = window.get("end")
        if start and end:
            return f"Quarter starting {start}"
        return "Last quarter"
    if window_type == "single_month":
        start = window.get("start")
        if start:
            return f"Month = {start}"
        return "Single month"
    if window_type == "ytd":
        return "Year to date"
    if window_type == "absolute":
        start = window.get("start")
        end = window.get("end")
        if start and end:
            return f"{start} to {end}"
        if start:
            return f"Since {start}"
    return window_type.replace("_", " ").title() if window_type else None


def _build_chips_from_nql(nql_payload: Optional[Dict[str, Any]]) -> Dict[str, List[str]]:
    if not nql_payload:
        return {"dimensions": [], "filters": [], "time": []}

    dims: List[str] = []
    for dim in nql_payload.get("dimensions", []):
        if dim and dim not in dims and dim != "month":
            dims.append(dim)
    for group_dim in nql_payload.get("group_by", []):
        if group_dim and group_dim not in dims and group_dim != "month":
            dims.append(group_dim)

    filter_chips: List[str] = []
    for filt in nql_payload.get("filters", []):
        field = filt.get("field")
        if field == "month":
            continue
        op = filt.get("op")
        value = filt.get("value")
        if isinstance(value, list):
            value_str = ", ".join(str(v) for v in value)
        else:
            value_str = str(value)
        filter_chips.append(f"{field} {op} {value_str}")

    time_window = _describe_time_window(nql_payload.get("time", {}).get("window"))
    time_chips = [time_window] if time_window else []

    return {
        "dimensions": dims,
        "filters": filter_chips,
        "time": time_chips,
    }


@app.post("/ask")
def ask(payload: AskRequest) -> Dict[str, Any]:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    executor: DuckDBExecutor = _state["executor"]
    resolver: PlanResolver = _state["resolver"]
    semantic = _state["semantic"]

    prefer_llm_env = os.getenv("INTENT_USE_LLM", "true").lower() in ("1", "true", "yes")
    prefer_llm = prefer_llm_env if payload.use_llm is None else bool(payload.use_llm)

    plan = build_plan(question, prefer_llm=prefer_llm)
    intent_engine = get_last_intent_engine()
    return _execute_query(plan, question, intent_engine=intent_engine)


def _build_conversation_response(response: Dict[str, Any]) -> Dict[str, Any]:
    response.setdefault("chips", _build_chips_from_nql(response.get("nql")))
    response.setdefault("status", "complete")
    return response


@app.post("/chat/complete")
def chat_complete(payload: ChatCompleteRequest) -> Dict[str, Any]:
    utterance = payload.utterance.strip()
    if not utterance:
        raise HTTPException(status_code=400, detail="Utterance cannot be empty.")

    session = _conversations.get(payload.session_id)
    if session.pending:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Pending clarification must be resolved first.",
                "question": session.pending.question,
                "missing_slots": session.pending.missing_slots,
            },
        )

    prefer_llm_env = os.getenv("INTENT_USE_LLM", "true").lower() in ("1", "true", "yes")
    prefer_llm = prefer_llm_env if payload.use_llm is None else bool(payload.use_llm)

    if session.last_nql:
        clarification = assess_ambiguity(session.last_nql, utterance)
        if clarification.needs_clarification:
            pending = _conversations.set_pending(
                payload.session_id,
                utterance,
                clarification.question or "Can you clarify?",
                clarification.missing_slots,
                clarification.suggested_answers,
                context=clarification.context,
            )
            chips = _build_chips_from_nql(session.last_nql)
            return {
                "status": "clarification_needed",
                "question": pending.question,
                "missing_slots": pending.missing_slots,
                "suggested_answers": pending.suggested_answers,
                "chips": chips,
            }

        try:
            merged_nql = rewrite_followup(session.last_nql, utterance)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        try:
            compiled = compile_payload(merged_nql)
        except NQLValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        response = _execute_query(compiled.plan, utterance, intent_engine="conversation")
        _conversations.update_last(
            payload.session_id, compiled.nql.dict(), response["plan"]
        )
        return _build_conversation_response(response)

    plan = build_plan(utterance, prefer_llm=prefer_llm)
    intent_engine = get_last_intent_engine()
    response = _execute_query(plan, utterance, intent_engine=intent_engine)
    nql_payload = response.get("nql")
    if nql_payload:
        _conversations.update_last(payload.session_id, nql_payload, response["plan"])
    else:
        session.last_plan = response["plan"]
    return _build_conversation_response(response)


@app.post("/chat/clarify")
def chat_clarify(payload: ChatClarifyRequest) -> Dict[str, Any]:
    answer = payload.answer.strip()
    if not answer:
        raise HTTPException(status_code=400, detail="Answer cannot be empty.")

    session = _conversations.get(payload.session_id)
    pending = session.pending
    if not pending:
        raise HTTPException(status_code=400, detail="No pending clarification for session.")
    if not session.last_nql:
        raise HTTPException(status_code=400, detail="No prior NQL state for clarification.")

    try:
        merged_nql = apply_clarification_answer(session.last_nql, pending, answer)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        compiled = compile_payload(merged_nql)
    except NQLValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    utterance = f"{pending.utterance} ({answer})"
    response = _execute_query(compiled.plan, utterance, intent_engine="conversation")
    _conversations.update_last(payload.session_id, compiled.nql.dict(), response["plan"])
    return _build_conversation_response(response)


@app.get("/explain_last")
def explain_last() -> Dict[str, Any]:
    if not _state.get("last_debug"):
        raise HTTPException(status_code=404, detail="No prior query.")
    return _state["last_debug"]
