"""Telemetry event logging helpers."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterator, Optional

from app.errors.taxonomy import ErrorType

__all__ = ["log_error", "log_feedback", "request_seen_recently", "feedback_rate_limited"]


@dataclass(frozen=True)
class _Config:
    log_relative_path: Path = Path("var") / "log" / "telemetry.ndjson"
    request_lookback: timedelta = timedelta(hours=24)
    feedback_window: timedelta = timedelta(hours=1)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _base_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _log_path() -> Path:
    override = os.getenv("TELEMETRY_LOG_PATH")
    if override:
        return Path(override).expanduser()
    return _base_dir() / _Config.log_relative_path


def _ensure_log_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _serialize_details(details: Dict[str, object]) -> Dict[str, object]:
    if not isinstance(details, dict):
        raise TypeError("details must be a dict")
    try:
        json.dumps(details)
    except TypeError as exc:  # pragma: no cover - defensive guard
        raise TypeError("details must be JSON serialisable") from exc
    return details


def _coerce_error_type(err_type: ErrorType | str) -> ErrorType:
    if isinstance(err_type, ErrorType):
        return err_type
    try:
        return ErrorType(err_type)
    except ValueError as exc:
        raise ValueError(f"Unknown error type: {err_type}") from exc


def _timestamp() -> str:
    return _now().isoformat().replace("+00:00", "Z")


def _append_event(event: Dict[str, object]) -> None:
    path = _log_path()
    _ensure_log_dir(path)
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    with path.open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")


def log_error(request_id: str, err_type: ErrorType | str, details: Dict[str, object]) -> Dict[str, object]:
    """Append an error telemetry event to the NDJSON log."""

    if not request_id or not isinstance(request_id, str):
        raise ValueError("request_id must be a non-empty string")
    coerced_type = _coerce_error_type(err_type)
    payload = {
        "type": "error",
        "timestamp": _timestamp(),
        "request_id": request_id,
        "error_type": coerced_type.value,
        "details": _serialize_details(details),
    }
    _append_event(payload)
    return payload


def log_feedback(
    request_id: str,
    helpful: bool,
    corrected_text: Optional[str] = None,
) -> Dict[str, object]:
    """Append a feedback telemetry event to the NDJSON log."""

    if not request_id or not isinstance(request_id, str):
        raise ValueError("request_id must be a non-empty string")
    if corrected_text is not None:
        cleaned = corrected_text.strip()
        corrected = cleaned or None
    else:
        corrected = None
    payload = {
        "type": "feedback",
        "timestamp": _timestamp(),
        "request_id": request_id,
        "helpful": bool(helpful),
    }
    if corrected:
        payload["corrected_text"] = corrected
    _append_event(payload)
    return payload


def _iter_events() -> Iterator[Dict[str, object]]:
    path = _log_path()
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict):
                    yield data
    except FileNotFoundError:  # pragma: no cover - race condition guard
        return


def _parse_timestamp(raw: object) -> Optional[datetime]:
    if not isinstance(raw, str):
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _event_recent(event: Dict[str, object], *, window: timedelta, now: Optional[datetime] = None) -> bool:
    timestamp = _parse_timestamp(event.get("timestamp"))
    if timestamp is None:
        return False
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    ref = now or _now()
    return timestamp >= ref - window


def request_seen_recently(request_id: str, *, now: Optional[datetime] = None) -> bool:
    if not request_id:
        return False
    lookback = _Config.request_lookback
    for event in _iter_events():
        if event.get("request_id") != request_id:
            continue
        if _event_recent(event, window=lookback, now=now):
            return True
    return False


def feedback_rate_limited(request_id: str, *, now: Optional[datetime] = None) -> bool:
    if not request_id:
        return False
    window = _Config.feedback_window
    for event in _iter_events():
        if event.get("type") != "feedback":
            continue
        if event.get("request_id") != request_id:
            continue
        if _event_recent(event, window=window, now=now):
            return True
    return False
