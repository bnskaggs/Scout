"""FastAPI entrypoint for the NL analytics proof-of-concept."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import guardrails, sql_builder, viz
from .executor import DuckDBExecutor
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
    try:
        resolved_plan = resolver.resolve(plan)
    except PlanResolutionError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc), "suggestions": exc.suggestions}) from exc

    sql = sql_builder.build(resolved_plan, semantic)
    try:
        guardrails.enforce(sql, resolved_plan)
    except guardrails.GuardrailError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = executor.query(sql)
    records = _apply_small_n(resolved_plan, result.records)
    chart = viz.choose_chart(resolved_plan, records)
    narrative = viz.build_narrative(resolved_plan, records)

    metric_defs = {metric: semantic.metrics[metric].sql_expression() for metric in resolved_plan.get("metrics", [])}
    response = {
        "answer": narrative,
        "table": records,
        "chart": chart,
        "sql": sql,
        "plan": resolved_plan,
        "lineage": {
            "metric_defs": metric_defs,
            "time_window": resolved_plan.get("time_window_label", "All time"),
            "filters": _summarise_filters(resolved_plan.get("filters", [])),
            "source": _state.get("source_csv"),
            "runtime_ms": result.runtime_ms,
        },
    }
    response["intent_engine"] = intent_engine
    _state["last_debug"] = {
        "plan": resolved_plan,
        "sql": sql,
        "runtime_ms": result.runtime_ms,
        "rowcount": result.rowcount,
    }
    return response


@app.get("/explain_last")
def explain_last() -> Dict[str, Any]:
    if not _state.get("last_debug"):
        raise HTTPException(status_code=404, detail="No prior query.")
    return _state["last_debug"]
