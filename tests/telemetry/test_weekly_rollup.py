from __future__ import annotations

import importlib
import json
from datetime import datetime, timedelta, timezone

from app.errors.taxonomy import ErrorType


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def test_weekly_rollup_summary(tmp_path):
    log_path = tmp_path / "telemetry.ndjson"
    output_path = tmp_path / "weekly.json"

    now = datetime(2024, 1, 8, 12, tzinfo=timezone.utc)
    events = [
        {
            "type": "error",
            "timestamp": _iso(now - timedelta(days=2)),
            "request_id": "req-1",
            "error_type": ErrorType.VALUE_NOT_FOUND.value,
            "details": {
                "dimension": "region",
                "value": "west",
                "time_window": "2023-12",
                "message": "Region not found",
            },
        },
        {
            "type": "error",
            "timestamp": _iso(now - timedelta(days=3)),
            "request_id": "req-2",
            "error_type": "compile_error",
            "details": {"query": "orders by day"},
        },
        {
            "type": "error",
            "timestamp": _iso(now - timedelta(days=10)),
            "request_id": "req-old",
            "error_type": "zero_rows",
            "details": {"query": "stale"},
        },
        {
            "type": "feedback",
            "timestamp": _iso(now - timedelta(days=1)),
            "request_id": "req-1",
            "helpful": False,
            "corrected_text": "show west coast revenue",
        },
        {
            "type": "feedback",
            "timestamp": _iso(now - timedelta(days=1, hours=1)),
            "request_id": "req-2",
            "helpful": True,
            "corrected_text": "orders per day",
        },
        {
            "type": "feedback",
            "timestamp": _iso(now - timedelta(days=6)),
            "request_id": "req-3",
            "helpful": True,
            "corrected_text": "orders per day",
        },
    ]

    with log_path.open("w", encoding="utf-8") as handle:
        for event in events:
            json.dump(event, handle)
            handle.write("\n")

    rollup = importlib.import_module("scripts.weekly_rollup")
    importlib.reload(rollup)

    summary = rollup.generate_weekly_summary(
        log_path=log_path,
        output_path=output_path,
        now=now,
        top_n=20,
    )

    assert output_path.exists()
    saved_summary = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved_summary == summary

    assert summary["error_counts"] == {
        ErrorType.VALUE_NOT_FOUND.value: 1,
        ErrorType.COMPILE_ERROR.value: 1,
    }

    assert summary["top_error_queries"][0] == {
        "query": "region=west | 2023-12 | Region not found",
        "count": 1,
    }
    assert summary["top_error_queries"][1] == {"query": "orders by day", "count": 1}

    assert summary["top_corrected_phrasings"][0] == {"text": "orders per day", "count": 2}
    assert summary["top_corrected_phrasings"][1] == {
        "text": "show west coast revenue",
        "count": 1,
    }
