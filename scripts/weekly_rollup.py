"""Weekly telemetry rollup script."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterator, Optional

from app.errors.taxonomy import ErrorType

LOG_RELATIVE_PATH = Path("var") / "log" / "telemetry.ndjson"
OUTPUT_RELATIVE_PATH = Path("var") / "log" / "weekly_summary.json"
CANDIDATE_QUERY_KEYS = (
    "query",
    "question",
    "utterance",
    "raw_query",
    "original_query",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_log_path() -> Path:
    return _repo_root() / LOG_RELATIVE_PATH


def _default_output_path() -> Path:
    return _repo_root() / OUTPUT_RELATIVE_PATH


def _parse_timestamp(value: object) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _load_events(path: Path) -> Iterator[Dict[str, object]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                yield data


def _derive_query_label(details: Dict[str, object]) -> str:
    if not isinstance(details, dict):
        return "unknown"
    for key in CANDIDATE_QUERY_KEYS:
        value = details.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    snapshot = details.get("nql_snapshot")
    if isinstance(snapshot, dict):
        for key in CANDIDATE_QUERY_KEYS:
            value = snapshot.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    parts: list[str] = []
    dimension = details.get("dimension")
    value = details.get("value")
    time_window = details.get("time_window")
    message = details.get("message")
    if dimension and value:
        parts.append(f"{dimension}={value}")
    elif dimension:
        parts.append(str(dimension))
    if time_window:
        parts.append(str(time_window))
    if message:
        parts.append(str(message))
    if parts:
        return " | ".join(parts)
    return "unknown"


def _sorted_items(
    counter: Counter[str], *, limit: int, key_name: str, tie_break: Optional[Dict[str, float]] = None
) -> list[dict[str, object]]:
    def _sort_key(item: tuple[str, int]) -> tuple[float, float, str]:
        key, count = item
        if tie_break and key in tie_break:
            # Newer timestamps should sort ahead of older ones.
            return (-count, -tie_break[key], key)
        return (-count, 0.0, key)

    items = sorted(counter.items(), key=_sort_key)
    return [{key_name: key, "count": count} for key, count in items[:limit]]


def generate_weekly_summary(
    log_path: Path | None = None,
    output_path: Path | None = None,
    *,
    now: Optional[datetime] = None,
    top_n: int = 20,
) -> Dict[str, object]:
    log_file = log_path or _default_log_path()
    output_file = output_path or _default_output_path()
    reference_time = now or datetime.now(timezone.utc)
    window_start = reference_time - timedelta(days=7)

    error_counts: Counter[str] = Counter()
    query_counter: Counter[str] = Counter()
    query_last_seen: Dict[str, float] = {}
    synonym_counter: Counter[str] = Counter()

    for event in _load_events(log_file):
        timestamp = _parse_timestamp(event.get("timestamp"))
        if timestamp is None or timestamp < window_start:
            continue
        event_type = event.get("type")
        if event_type == "error":
            error_type_value = event.get("error_type")
            try:
                error_type = ErrorType(error_type_value).value
            except ValueError:
                error_type = ErrorType.UNKNOWN.value
            error_counts[error_type] += 1
            details_obj = event.get("details")
            details = details_obj if isinstance(details_obj, dict) else {}
            query_label = _derive_query_label(details)
            query_counter[query_label] += 1
            query_last_seen[query_label] = timestamp.timestamp()
        elif event_type == "feedback":
            corrected = event.get("corrected_text")
            if isinstance(corrected, str) and corrected.strip():
                synonym_counter[corrected.strip()] += 1

    summary = {
        "generated_at": reference_time.isoformat().replace("+00:00", "Z"),
        "week_start": window_start.isoformat().replace("+00:00", "Z"),
        "week_end": reference_time.isoformat().replace("+00:00", "Z"),
        "error_counts": dict(sorted(error_counts.items())),
        "top_error_queries": _sorted_items(
            query_counter, limit=top_n, key_name="query", tie_break=query_last_seen
        ),
        "top_corrected_phrasings": _sorted_items(
            synonym_counter, limit=top_n, key_name="text"
        ),
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate weekly telemetry summary")
    parser.add_argument("--log-path", type=Path, default=None, help="Override telemetry log path")
    parser.add_argument(
        "--output-path", type=Path, default=None, help="Override weekly summary output path"
    )
    parser.add_argument("--top", type=int, default=20, help="Number of top rows to include")
    args = parser.parse_args()
    generate_weekly_summary(args.log_path, args.output_path, top_n=args.top)


if __name__ == "__main__":
    main()
