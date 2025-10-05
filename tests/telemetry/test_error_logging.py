from __future__ import annotations

import importlib
import json

from app.errors.taxonomy import ErrorType


def test_log_error_writes_ndjson(tmp_path, monkeypatch):
    log_path = tmp_path / "telemetry.ndjson"
    monkeypatch.setenv("TELEMETRY_LOG_PATH", str(log_path))
    events = importlib.import_module("app.telemetry.events")
    importlib.reload(events)

    details = {
        "nql_snapshot": {"query": "revenue by region"},
        "time_window": "last_7_days",
        "dimension": "region",
        "value": "west",
        "message": "Region not found",
    }
    event = events.log_error("req-123", ErrorType.VALUE_NOT_FOUND, details)

    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    stored = json.loads(lines[0])
    assert stored["type"] == "error"
    assert stored["request_id"] == "req-123"
    assert stored["error_type"] == ErrorType.VALUE_NOT_FOUND.value
    assert stored["details"] == details
    assert stored["timestamp"].endswith("Z")
    assert event == stored
