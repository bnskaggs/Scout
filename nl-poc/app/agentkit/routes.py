"""FastAPI router exposing an OpenAI AgentKit bridge."""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

try:  # pragma: no cover - standard runtime import
    from fastapi import APIRouter, HTTPException
    from fastapi.responses import JSONResponse
except Exception:  # pragma: no cover - tests stub out fastapi
    class HTTPException(Exception):  # type: ignore[misc, override]
        def __init__(self, status_code: int, detail: Any):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class APIRouter:  # type: ignore[override]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.routes: List[Any] = []

        def post(self, _path: str, **_kwargs: Any):
            def decorator(func):
                return func

            return decorator

    class JSONResponse(dict):  # type: ignore[override]
        def __init__(self, *, content: Dict[str, Any], status_code: int = 200) -> None:
            super().__init__(content)
            self.status_code = status_code

from pydantic import BaseModel, Field

from . import tools

try:  # pragma: no cover - exercised at runtime
    from openai import OpenAI
except Exception:  # pragma: no cover - defensive: SDK might be missing
    OpenAI = None  # type: ignore


router = APIRouter(prefix="/agent", tags=["agent"])

_DEFAULT_AGENT_MODEL = os.getenv("AGENTKIT_MODEL", os.getenv("LLM_MODEL", "gpt-4.1-mini"))
_AGENT_INSTRUCTIONS = (
    "You are Scout's analytics copilot. Use the provided tools to compile "
    "natural language analytics questions into SQL and concise summaries. "
    "Always reply with strictly valid JSON matching the schema: "
    "{\"table\": [...], \"chart\": {...}, \"sql\": \"...\", \"summary\": \"...\", \"warnings\": []}. "
    "Never hallucinate values; prefer returning warnings when data is missing."
)

_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "compile_plan_and_query",
            "description": "Compile a natural language question into SQL and deterministic records.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Original user utterance to analyse.",
                    },
                    "prefer_llm": {
                        "type": "boolean",
                        "description": "Force enabling the LLM-based planner even when disabled globally.",
                    },
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_and_validate",
            "description": "Summarise tabular results and surface guardrail warnings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan": {
                        "type": "object",
                        "description": "Resolved analytics plan returned by the compiler tool.",
                    },
                    "records": {
                        "type": "array",
                        "description": "Records returned by the DuckDB execution stage.",
                        "items": {"type": "object"},
                    },
                    "sql": {
                        "type": "string",
                        "description": "SQL statement used to generate the records.",
                    },
                },
                "required": ["plan", "records"],
            },
        },
    },
]


class AgentRequest(BaseModel):
    """Inbound payload received from ChatKit."""

    message: str = Field(..., description="Latest user utterance.")
    thread_id: Optional[str] = Field(None, description="Existing OpenAI thread identifier.")
    session_id: Optional[str] = Field(
        None,
        description="Opaque ChatKit session identifier used to restore threads between requests.",
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context to persist with the thread.")
    model: Optional[str] = Field(None, description="Override OpenAI model to use for the agent run.")


class AgentResponse(BaseModel):
    """Response returned to ChatKit."""

    thread_id: str
    table: List[Dict[str, Any]]
    chart: Dict[str, Any]
    sql: str
    summary: str
    warnings: List[str]


class _ThreadStore:
    """Simple in-memory persistence of thread ids keyed by session id."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._threads: Dict[str, str] = {}

    def get(self, session_id: Optional[str]) -> Optional[str]:
        if not session_id:
            return None
        with self._lock:
            return self._threads.get(session_id)

    def set(self, session_id: Optional[str], thread_id: str) -> None:
        if not session_id:
            return
        with self._lock:
            self._threads[session_id] = thread_id


_thread_store = _ThreadStore()
_assistant_cache: Dict[str, str] = {}
_assistant_lock = threading.Lock()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def _ensure_client() -> Any:
    if OpenAI is None:
        raise HTTPException(status_code=503, detail="openai SDK is not installed")
    try:
        return OpenAI()
    except Exception as exc:  # pragma: no cover - network/init errors
        raise HTTPException(status_code=503, detail=f"Failed to initialise OpenAI client: {exc}") from exc


def _ensure_agent(client: Any, model: str) -> str:
    with _assistant_lock:
        cached = _assistant_cache.get(model)
        if cached:
            return cached
        assistant = client.beta.assistants.create(
            name="Scout Analytics Agent",
            instructions=_AGENT_INSTRUCTIONS,
            model=model,
            tools=_TOOL_DEFINITIONS,
        )
        _assistant_cache[model] = assistant.id
        return assistant.id


def _resolve_thread(client: Any, payload: AgentRequest) -> str:
    thread_id = payload.thread_id or _thread_store.get(payload.session_id)
    if thread_id:
        return thread_id
    metadata = payload.metadata.copy()
    if payload.session_id:
        metadata.setdefault("session_id", payload.session_id)
    thread = client.beta.threads.create(metadata=metadata or None)
    _thread_store.set(payload.session_id, thread.id)
    return thread.id


def _dispatch_tool_call(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if name == "compile_plan_and_query":
        result = tools.compile_plan_and_query(**arguments)
        return result.dict()
    if name == "summarize_and_validate":
        result = tools.summarize_and_validate(**arguments)
        return result.dict()
    raise HTTPException(status_code=500, detail=f"Unsupported tool invocation: {name}")


def _collect_assistant_reply(client: Any, thread_id: str) -> Dict[str, Any]:
    messages = client.beta.threads.messages.list(thread_id=thread_id, order="desc", limit=1)
    if not messages.data:
        raise HTTPException(status_code=500, detail="Agent did not return a response")
    message = messages.data[0]
    buffer: List[str] = []
    for part in message.content:
        if getattr(part, "type", None) == "text":
            buffer.append(part.text.value)
    raw_text = "".join(buffer).strip()
    if not raw_text:
        raise HTTPException(status_code=500, detail="Agent response was empty")
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Agent response was not valid JSON: {exc}") from exc
    for key in ("table", "chart", "sql", "summary", "warnings"):
        if key not in parsed:
            raise HTTPException(status_code=500, detail=f"Agent response missing key: {key}")
    return parsed


def _run_agent(client: Any, assistant_id: str, thread_id: str, payload: AgentRequest) -> Dict[str, Any]:
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=payload.message,
    )
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
    )
    while True:
        run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        status = getattr(run, "status", None)
        if status in {"queued", "in_progress"}:
            time.sleep(0.3)
            continue
        if status == "requires_action":
            required = getattr(run, "required_action", None)
            if not required:
                raise HTTPException(status_code=500, detail="Agent run requires action without tool calls")
            tool_calls = getattr(required.submit_tool_outputs, "tool_calls", [])
            outputs = []
            for call in tool_calls:
                name = getattr(call.function, "name", "")
                arguments_json = getattr(call.function, "arguments", "{}")
                try:
                    arguments = json.loads(arguments_json)
                except json.JSONDecodeError as exc:
                    raise HTTPException(status_code=400, detail=f"Invalid tool arguments: {exc}") from exc
                result = _dispatch_tool_call(name, arguments)
                outputs.append({"tool_call_id": call.id, "output": _json_dumps(result)})
            run = client.beta.threads.runs.submit_tool_outputs(
                thread_id=thread_id,
                run_id=run.id,
                tool_outputs=outputs,
            )
            continue
        if status == "completed":
            return _collect_assistant_reply(client, thread_id)
        if status in {"failed", "cancelled", "expired"}:
            raise HTTPException(status_code=500, detail=f"Agent run terminated with status={status}")
        time.sleep(0.3)


@router.post("", response_model=AgentResponse)
def agent_entrypoint(payload: AgentRequest) -> JSONResponse:
    """Primary endpoint consumed by ChatKit."""

    client = _ensure_client()
    model = payload.model or _DEFAULT_AGENT_MODEL
    assistant_id = _ensure_agent(client, model)
    thread_id = _resolve_thread(client, payload)
    _thread_store.set(payload.session_id, thread_id)

    response_payload = _run_agent(client, assistant_id, thread_id, payload)
    response_payload_sorted = json.loads(_json_dumps(response_payload))
    response_payload_sorted["thread_id"] = thread_id

    validated = AgentResponse(thread_id=thread_id, **response_payload_sorted)
    return JSONResponse(content=json.loads(_json_dumps(validated.dict())))


def ensure_agent_runtime(model: Optional[str] = None) -> Tuple[Any, str, str]:
    """Return an OpenAI client, assistant id, and resolved model for the analytics agent."""

    resolved_model = model or _DEFAULT_AGENT_MODEL
    client = _ensure_client()
    assistant_id = _ensure_agent(client, resolved_model)
    return client, assistant_id, resolved_model


__all__ = ["router", "ensure_agent_runtime"]
