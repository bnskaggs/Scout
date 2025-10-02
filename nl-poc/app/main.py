"""FastAPI entrypoint for the NL analytics proof-of-concept."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb
from fastapi import FastAPI, HTTPException, Header
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
from .llm_client import _load_env_once

from .nql import NQLValidationError, compile_payload, use_nql_enabled
from .planner import build_plan, get_last_intent_engine, get_last_nql_status

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

    session_id: Optional[str] = None

    utterance: str
    use_llm: Optional[bool] = None


class ChatClarifyRequest(BaseModel):

    session_id: Optional[str] = None

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

logger = logging.getLogger(__name__)

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


def _slug_reason(message: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", message.lower()).strip("_")
    return slug or "error"


def _env_truthy(value: Optional[str], *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _gather_nql_debug_snapshot() -> Dict[str, Any]:
    _load_env_once()
    use_nql_raw = os.getenv("USE_NQL")
    provider = (os.getenv("LLM_PROVIDER") or "").strip()
    model = (os.getenv("LLM_MODEL") or "").strip()
    snapshot = {
        "use_nql": use_nql_enabled(),
        "use_nql_raw": use_nql_raw,
        "llm_provider": provider,
        "model": model,
        "api_key_present": bool(os.getenv("LLM_API_KEY")),
        "retriever_enabled": _env_truthy(os.getenv("RETRIEVER_ENABLED")),
    }
    return snapshot


def _resolve_session_id(body_value: Optional[str], header_value: Optional[str]) -> str:
    session_id = header_value or body_value
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    return session_id


def _build_nql_failure(stage: str, error: Exception) -> Dict[str, Any]:
    message = str(error)
    return {
        "attempted": True,
        "valid": False,
        "stage": stage,
        "reason": _slug_reason(message),
        "detail": message,
        "fallback": "legacy",
    }


def _build_gate_status(reason: str) -> Dict[str, Any]:
    status: Dict[str, Any] = {"attempted": False, "stage": "gate", "reason": reason}
    if reason != "clarifier_pending":
        status["fallback"] = "legacy"
    return status


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
    snapshot = _gather_nql_debug_snapshot()
    logger.info(
        "nql_gate_config use_nql_raw=%s use_nql=%s llm_provider=%s llm_model=%s api_key_present=%s retriever_enabled=%s",
        snapshot.get("use_nql_raw"),
        snapshot["use_nql"],
        snapshot["llm_provider"],
        snapshot["model"],
        snapshot["api_key_present"],
        snapshot["retriever_enabled"],
    )


@app.on_event("shutdown")
def shutdown_event() -> None:
    executor: DuckDBExecutor = _state.get("executor")
    if executor:
        executor.close()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/chat/debug-nql")
def chat_debug_nql() -> Dict[str, Any]:
    snapshot = _gather_nql_debug_snapshot()
    return {
        "use_nql": snapshot["use_nql"],
        "llm_provider": snapshot["llm_provider"],
        "model": snapshot["model"],
        "api_key_present": snapshot["api_key_present"],
        "retriever_enabled": snapshot["retriever_enabled"],
    }


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

def chat_complete(
    payload: ChatCompleteRequest,
    x_session_id: Optional[str] = Header(None, alias="X-Session-Id"),
) -> Dict[str, Any]:
    session_id = _resolve_session_id(payload.session_id, x_session_id)

    utterance = payload.utterance.strip()
    if not utterance:
        raise HTTPException(status_code=400, detail="Utterance cannot be empty.")


    session = _conversations.get(session_id)

    if session.pending:
        gate_status = _build_gate_status("clarifier_pending")
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Pending clarification must be resolved first.",
                "question": session.pending.question,
                "missing_slots": session.pending.missing_slots,
                "nql_status": gate_status,
            },
        )

    prefer_llm_env = os.getenv("INTENT_USE_LLM", "true").lower() in ("1", "true", "yes")
    prefer_llm = prefer_llm_env if payload.use_llm is None else bool(payload.use_llm)

    snapshot = _gather_nql_debug_snapshot()
    use_nql = snapshot["use_nql"]
    llm_config_present = bool(
        snapshot["llm_provider"] and snapshot["model"] and snapshot["api_key_present"]
    )
    feature_disabled = _env_truthy(os.getenv("NQL_FEATURE_DISABLED"))

    gate_status: Optional[Dict[str, Any]] = None
    if feature_disabled:
        gate_status = _build_gate_status("feature_disabled")
    elif not use_nql:
        gate_status = _build_gate_status("use_nql_flag_false")
    elif not llm_config_present:
        gate_status = _build_gate_status("missing_llm_config")

    nql_failure_status: Optional[Dict[str, Any]] = None

    if gate_status is None and session.last_nql:
        clarification = assess_ambiguity(session.last_nql, utterance)
        if clarification.needs_clarification:
            pending = _conversations.set_pending(
                session_id,
                utterance,
                clarification.question or "Can you clarify?",
                clarification.missing_slots,
                clarification.suggested_answers,
                context=clarification.context,
            )
            chips = _build_chips_from_nql(session.last_nql)
            status = _build_gate_status("clarifier_pending")
            response_data = {
                "status": "clarification_needed",
                "question": pending.question,
                "missing_slots": pending.missing_slots,
                "suggested_answers": pending.suggested_answers,
                "chips": chips,
                "engine": "nql",
                "nql_status": status,
            }
            return response_data

        try:
            merged_nql = rewrite_followup(session.last_nql, utterance)
        except ValueError as exc:
            nql_failure_status = _build_nql_failure("generator", exc)
        else:
            try:
                compiled = compile_payload(merged_nql)
            except NQLValidationError as exc:
                nql_failure_status = _build_nql_failure("validator", exc)
            except Exception as exc:  # pragma: no cover - defensive guard
                nql_failure_status = _build_nql_failure("compiler", exc)
            else:
                response = _execute_query(compiled.plan, utterance, intent_engine="nql")
                response["engine"] = "nql"
                response["nql_status"] = {"attempted": True, "valid": True}
                _conversations.update_last(session_id, compiled.nql.dict(), response["plan"])
                return _build_conversation_response(response)

    plan = build_plan(utterance, prefer_llm=prefer_llm)
    planner_status = get_last_nql_status() if gate_status is None else None
    execution_engine = "legacy" if gate_status else ("nql" if plan.get("_nql") else "legacy")
    response = _execute_query(plan, utterance, intent_engine=execution_engine)
    response["engine"] = execution_engine
    nql_payload = response.get("nql")

    if gate_status:
        response["nql_status"] = gate_status
        session.last_plan = response["plan"]
    elif nql_payload and execution_engine == "nql":
        response["nql_status"] = planner_status or {"attempted": True, "valid": True}
        _conversations.update_last(session_id, nql_payload, response["plan"])
    else:
        status = nql_failure_status or planner_status or {"attempted": False}
        response["nql_status"] = status
        session.last_plan = response["plan"]

    return _build_conversation_response(response)


@app.post("/chat/clarify")

def chat_clarify(
    payload: ChatClarifyRequest,
    x_session_id: Optional[str] = Header(None, alias="X-Session-Id"),
) -> Dict[str, Any]:
    session_id = _resolve_session_id(payload.session_id, x_session_id)

    answer = payload.answer.strip()
    if not answer:
        raise HTTPException(status_code=400, detail="Answer cannot be empty.")


    session = _conversations.get(session_id)

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

    response = _execute_query(compiled.plan, utterance, intent_engine="nql")
    response["engine"] = "nql"
    response["nql_status"] = {"attempted": True, "valid": True}
    _conversations.update_last(session_id, compiled.nql.dict(), response["plan"])
    return _build_conversation_response(response)


@app.get("/chat/debug-state")
def chat_debug_state(session_id: str) -> Dict[str, Any]:
    state = _conversations.peek(session_id)
    if not state:
        return {"has_state": False, "last_nql": None}
    return {"has_state": state.last_nql is not None, "last_nql": state.last_nql}



@app.get("/explain_last")
def explain_last() -> Dict[str, Any]:
    if not _state.get("last_debug"):
        raise HTTPException(status_code=404, detail="No prior query.")
    return _state["last_debug"]
