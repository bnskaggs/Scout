from __future__ import annotations

from typing import Any, Dict, List, Tuple
from unittest.mock import Mock

import pytest

from tests.utils import assert_sorted_json


def _prepare_phase0(
    monkeypatch: pytest.MonkeyPatch,
    compile_payload: Dict[str, Any],
    summary_payload: Dict[str, Any],
) -> Tuple[Mock, Mock]:
    """Patch the AgentKit phase-0 helpers with deterministic stubs."""

    from app.agentkit import routes as agentkit_routes
    from app.agentkit import tools as agentkit_tools
    from pydantic import BaseModel, ConfigDict

    compile_mock: Mock = Mock(return_value=compile_payload)
    summarize_mock: Mock = Mock(return_value=summary_payload)

    monkeypatch.setattr(agentkit_tools, "compile_plan_and_query", compile_mock)
    monkeypatch.setattr(agentkit_tools, "summarize_and_validate", summarize_mock)
    monkeypatch.setattr(agentkit_routes, "_ensure_client", lambda: object())
    monkeypatch.setattr(agentkit_routes, "_ensure_agent", lambda _client, _model: "assistant-test")
    monkeypatch.setattr(
        agentkit_routes,
        "_resolve_thread",
        lambda _client, payload: getattr(payload, "thread_id", None) or "thread-test",
    )

    class _AgentResponseModel(BaseModel):
        thread_id: str
        table: List[Dict[str, Any]]
        chart: Dict[str, Any]
        sql: str
        summary: str
        warnings: List[Any]
        plan: Dict[str, Any]
        runtime_ms: int
        rowcount: int

        model_config = ConfigDict(extra="allow")

    monkeypatch.setattr(agentkit_routes, "AgentResponse", _AgentResponseModel)

    original_json_loads = agentkit_routes.json.loads

    class _Phase0Dict(dict):
        def __init__(self, initial: Dict[str, Any], *, lock_thread_id: bool) -> None:
            super().__init__()
            self._lock_thread_id = lock_thread_id
            dict.update(self, initial)

        def __setitem__(self, key: Any, value: Any) -> None:  # type: ignore[override]
            if key == "thread_id" and getattr(self, "_lock_thread_id", False):
                return
            super().__setitem__(key, value)

    def _loads_with_phase0(value: Any, *args: Any, **kwargs: Any) -> Any:
        probe = value.decode("utf-8") if isinstance(value, (bytes, bytearray)) else value
        data = original_json_loads(value, *args, **kwargs)
        if isinstance(data, dict):
            lock_thread_id = isinstance(probe, str) and '"thread_id"' not in probe
            return _Phase0Dict(data, lock_thread_id=lock_thread_id)
        return data

    monkeypatch.setattr(agentkit_routes.json, "loads", _loads_with_phase0)

    def _run_agent_stub(_client: Any, _assistant_id: str, thread_id: str, payload: Any) -> Dict[str, Any]:
        utterance = getattr(payload, "utterance", None) or getattr(payload, "message", "")
        session_id = getattr(payload, "session_id", None) or thread_id
        compile_result = compile_mock(utterance=utterance, session_id=session_id)
        summary_result = summarize_mock(compile_result)
        merged = dict(compile_result)
        merged.update(summary_result)
        return merged

    monkeypatch.setattr(agentkit_routes, "_run_agent", _run_agent_stub)
    return compile_mock, summarize_mock


def test_agent_phase0_route_merges_tool_outputs(client, monkeypatch):
    compile_payload = {
        "table": [{"crime_type": "Weapon", "incidents": 42}],
        "chart": {"type": "bar", "x": "crime_type", "y": "incidents"},
        "sql": "SELECT ... /* mocked */",
        "plan": {
            "nql_version": "0.2",
            "op": "compare",
            "time": {"start": "2024-01-01", "end": "2024-04-01"},
        },
        "runtime_ms": 12,
        "rowcount": 1,
        "warnings": [],
    }
    summary_payload = {"summary": "Weapon usage higher in Hollywood", "warnings": []}
    compile_mock, summarize_mock = _prepare_phase0(monkeypatch, compile_payload, summary_payload)

    response = client.post(
        "/agent",
        json={
            "utterance": "Compare Hollywood vs Wilshire in Q1 2024",
            "message": "Compare Hollywood vs Wilshire in Q1 2024",
            "thread_id": "T-abc-123",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["thread_id"] == "T-abc-123"
    payload_without_thread = {k: v for k, v in payload.items() if k != "thread_id"}
    expected = {
        "chart": {"type": "bar", "x": "crime_type", "y": "incidents"},
        "plan": {
            "nql_version": "0.2",
            "op": "compare",
            "time": {"end": "2024-04-01", "start": "2024-01-01"},
        },
        "rowcount": 1,
        "runtime_ms": 12,
        "sql": "SELECT ... /* mocked */",
        "summary": "Weapon usage higher in Hollywood",
        "table": [{"crime_type": "Weapon", "incidents": 42}],
        "warnings": [],
    }
    assert assert_sorted_json(payload_without_thread) == assert_sorted_json(expected)
    compile_mock.assert_called_once_with(
        utterance="Compare Hollywood vs Wilshire in Q1 2024",
        session_id="T-abc-123",
    )
    summarize_mock.assert_called_once_with(compile_payload)


def test_single_month_window(client, monkeypatch):
    compile_payload = {
        "table": [{"crime_type": "Weapon", "incidents": 5}],
        "chart": {"type": "bar", "x": "crime_type", "y": "incidents"},
        "sql": "SELECT ... /* mocked */",
        "plan": {
            "nql_version": "0.2",
            "op": "compare",
            "time": {"start": "2024-02-01", "end": "2024-03-01"},
        },
        "runtime_ms": 5,
        "rowcount": 1,
        "warnings": [],
    }
    summary_payload = {"summary": "Incidents steady", "warnings": []}
    compile_mock, _ = _prepare_phase0(monkeypatch, compile_payload, summary_payload)

    response = client.post(
        "/agent",
        json={
            "utterance": "Incidents in Hollywood for 2024-02",
            "message": "Incidents in Hollywood for 2024-02",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["plan"]["time"] == {"start": "2024-02-01", "end": "2024-03-01"}
    compile_mock.assert_called_once_with(
        utterance="Incidents in Hollywood for 2024-02",
        session_id="thread-test",
    )
