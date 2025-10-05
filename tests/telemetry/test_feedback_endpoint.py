from __future__ import annotations

import importlib
import json

import pytest
from fastapi import HTTPException

from app.errors.taxonomy import ErrorType


def _reload_modules():
    events = importlib.import_module("app.telemetry.events")
    feedback = importlib.import_module("app.http.feedback")
    events_module = importlib.reload(events)
    feedback_module = importlib.reload(feedback)
    return events_module, feedback_module


def test_feedback_endpoint_validates_request_id(tmp_path, monkeypatch):
    log_path = tmp_path / "telemetry.ndjson"
    monkeypatch.setenv("TELEMETRY_LOG_PATH", str(log_path))
    events, feedback = _reload_modules()

    events.log_error(
        "req-ok",
        ErrorType.VALUE_NOT_FOUND,
        {
            "nql_snapshot": {"query": "revenue by region"},
            "time_window": "2024-01-01/2024-01-31",
            "dimension": "region",
            "value": "west",
            "message": "Region not found",
        },
    )

    request_model = feedback.FeedbackRequest(
        request_id="req-ok", helpful=False, corrected_text="try 'west region'"
    )
    payload = feedback.submit_feedback(request_model)
    assert payload["status"] == "ok"

    with pytest.raises(HTTPException) as rate_limit:
        feedback.submit_feedback(feedback.FeedbackRequest(request_id="req-ok", helpful=True))
    assert rate_limit.value.status_code == 429

    with pytest.raises(HTTPException) as missing:
        feedback.submit_feedback(feedback.FeedbackRequest(request_id="unknown", helpful=True))
    assert missing.value.status_code == 404

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2  # one error + one feedback
    stored_feedback = json.loads(lines[1])
    assert stored_feedback["type"] == "feedback"
    assert stored_feedback["request_id"] == "req-ok"
    assert stored_feedback["corrected_text"] == "try 'west region'"
