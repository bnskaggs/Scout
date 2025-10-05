"""Pytest harness that replays multi-turn evaluation scripts."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pytest

from . import shared_fixtures

PlanResolver = shared_fixtures.PlanResolver
PlanResolutionError = shared_fixtures.PlanResolutionError

CASE_DIR = Path(__file__).parent / "cases"
ARTIFACT_ROOT = Path(".eval_artifacts")


@dataclass
class TurnRecord:
    utterance: str
    before: Dict[str, Any]
    after: Dict[str, Any]


@dataclass
class EvalResult:
    final_nql: Dict[str, Any]
    resolved_plan: Optional[Dict[str, Any]]
    sql: Optional[str]
    snapshot: Dict[str, Any]
    error_message: Optional[str]
    history: List[TurnRecord]


def _load_case(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text())
    data.setdefault("name", path.stem.replace("_", " "))
    return data


def _assert_partial(expected: Any, actual: Any, context: str = "") -> None:
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{context} expected dict, got {type(actual)}"
        for key, value in expected.items():
            assert key in actual, f"Missing key {context + key}"
            _assert_partial(value, actual[key], context=f"{context}{key}.")
        return
    if isinstance(expected, list):
        assert isinstance(actual, list), f"{context} expected list, got {type(actual)}"
        if expected and isinstance(expected[0], str) and actual and isinstance(actual[0], dict):
            aliases = []
            for item in actual:
                if isinstance(item, dict):
                    alias = item.get("alias") or item.get("name")
                else:
                    alias = item
                aliases.append(alias)
            assert expected == aliases, f"Mismatch at {context}: expected {expected}, got {aliases}"
            return
        assert len(expected) == len(actual), f"Length mismatch at {context}: expected {len(expected)}, got {len(actual)}"
        for index, (exp_item, act_item) in enumerate(zip(expected, actual)):
            _assert_partial(exp_item, act_item, context=f"{context}{index}.")
        return
    assert expected == actual, f"Mismatch at {context}: expected {expected}, got {actual}"


def _format_time_from_plan(plan: Optional[Dict[str, Any]], nql: Dict[str, Any]) -> Optional[str]:
    filters = (plan or {}).get("filters", [])
    for filt in filters:
        if isinstance(filt, dict) and filt.get("field") == "month":
            value = filt.get("value")
            if isinstance(value, list):
                start = value[0] if value else None
                end = value[1] if len(value) > 1 else None
                if start and end:
                    return f"{start}..{end}"
                return start or end
            if value is not None:
                return str(value)
    window = nql.get("time", {}).get("window", {})
    start = window.get("start")
    end = window.get("end")
    if start and end:
        return f"{start}..{end}"
    return start or end


def _infer_action(record: Optional[TurnRecord], error: Optional[str]) -> str:
    if error:
        return "value_not_found_fallback"
    if not record:
        return "fresh_query"
    before = record.before
    after = record.after
    notes = after.get("provenance", {}).get("retrieval_notes") or []
    if any(str(note).startswith("topic_shift") for note in notes):
        return "fresh_query"
    if after.get("dimensions") != before.get("dimensions") or after.get("group_by") != before.get("group_by"):
        return "replace_dimension"
    if after.get("metrics") != before.get("metrics"):
        return "change_metric"
    if after.get("time", {}).get("window") != before.get("time", {}).get("window"):
        return "adjust_time"
    if after.get("compare") != before.get("compare"):
        compare = after.get("compare")
        if isinstance(compare, dict) and compare.get("type"):
            compare_type = compare.get("type")
            return f"toggle_{compare_type}"
        return "toggle_compare"
    if after.get("filters") != before.get("filters"):
        return "refine_filters"
    return "refine"


def _build_snapshot(result: EvalResult) -> Dict[str, Any]:
    record = result.history[-1] if result.history else None
    action = _infer_action(record, result.error_message)
    plan = result.resolved_plan or {}
    group_by = plan.get("group_by") or []
    group_repr: Optional[str]
    if isinstance(group_by, list):
        group_repr = ", ".join(group_by) if group_by else None
    else:
        group_repr = str(group_by)
    time_repr = _format_time_from_plan(result.resolved_plan, result.final_nql)
    snapshot = {
        "action": action,
        "group_by": group_repr,
        "time": time_repr,
    }
    return snapshot


def replay_case(
    case_data: Dict[str, Any],
    *,
    base_state: Dict[str, Any],
    resolver: PlanResolver,
    compile_fn,
    sql_builder,
    today: date,
) -> EvalResult:
    state = deepcopy(base_state)
    history: List[TurnRecord] = []
    for turn in case_data.get("turns", []):
        utterance = turn["user"].strip()
        next_state = shared_fixtures.rewrite_followup(state, utterance, today=today)
        history.append(TurnRecord(utterance=utterance, before=deepcopy(state), after=deepcopy(next_state)))
        state = next_state

    compiled = compile_fn(state, today=today)
    error_message: Optional[str] = None
    resolved_plan: Optional[Dict[str, Any]]
    sql: Optional[str]
    try:
        resolved_plan = resolver.resolve(compiled.plan)
        sql = sql_builder(resolved_plan)
    except PlanResolutionError as exc:
        error_message = str(exc)
        resolved_plan = None
        sql = None

    result = EvalResult(
        final_nql=state,
        resolved_plan=resolved_plan,
        sql=sql,
        snapshot={},  # populated after inference
        error_message=error_message,
        history=history,
    )
    result.snapshot = _build_snapshot(result)
    return result


def _write_artifacts(case_id: str, result: EvalResult) -> None:
    target = ARTIFACT_ROOT / case_id
    target.mkdir(parents=True, exist_ok=True)
    (target / "final_nql.json").write_text(json.dumps(result.final_nql, indent=2))
    if result.resolved_plan is not None:
        (target / "final_plan.json").write_text(json.dumps(result.resolved_plan, indent=2))
    if result.sql is not None:
        (target / "final.sql").write_text(result.sql)
    (target / "snapshot.json").write_text(json.dumps(result.snapshot, indent=2))
    if result.error_message:
        (target / "error.txt").write_text(result.error_message)


CASE_PATHS = sorted(CASE_DIR.glob("*.yaml"))


@pytest.mark.parametrize("case_path", CASE_PATHS, ids=lambda p: p.stem)
def test_eval_case(
    case_path: Path,
    base_state: Dict[str, Any],
    resolver,
    compiler,
    sql_builder,
    eval_today: date,
) -> None:
    data = _load_case(case_path)
    today_raw = data.get("today")
    today = date.fromisoformat(today_raw) if today_raw else eval_today
    result = replay_case(
        data,
        base_state=base_state,
        resolver=resolver,
        compile_fn=compiler,
        sql_builder=sql_builder,
        today=today,
    )

    try:
        expected = data.get("expect", {})
        expected_nql = expected.get("nql")
        if expected_nql:
            _assert_partial(expected_nql, result.final_nql)

        expected_snapshot = expected.get("snapshot")
        if expected_snapshot:
            _assert_partial(expected_snapshot, result.snapshot)

        expected_error = expected.get("error")
        if expected_error:
            assert result.error_message is not None, "Expected resolution error"
            message_contains = expected_error.get("message_contains")
            if message_contains:
                assert message_contains in result.error_message
        else:
            assert result.error_message is None, f"Unexpected resolver error: {result.error_message}"

        sql_contains: Iterable[str] = expected.get("sql_contains", []) or []
        if sql_contains:
            assert result.sql, "Expected SQL to be generated"
            for fragment in sql_contains:
                assert fragment in result.sql, f"Expected to find '{fragment}' in SQL"
        sql_not_contains: Iterable[str] = expected.get("sql_not_contains", []) or []
        if sql_not_contains and result.sql:
            for fragment in sql_not_contains:
                assert fragment not in result.sql, f"Unexpected SQL fragment '{fragment}'"
    except AssertionError:
        _write_artifacts(case_path.stem, result)
        raise


def load_all_cases(pattern: Optional[str] = None) -> List[Path]:
    if not pattern:
        return list(CASE_PATHS)
    return sorted(CASE_DIR.glob(pattern))


def run_cases_for_cli(pattern: Optional[str] = None) -> Dict[str, Any]:
    context = shared_fixtures.build_eval_context()
    compiler_fn = context["compiler"]
    sql_builder_fn = context["sql_builder"]
    resolver_obj = context["resolver"]
    base_state_template = context["base_state"]
    today_value = context["today"]

    results: Dict[str, Any] = {"passed": [], "failed": []}
    for path in load_all_cases(pattern):
        data = _load_case(path)
        case_id = path.stem
        base_state = deepcopy(base_state_template)
        today_raw = data.get("today")
        today = date.fromisoformat(today_raw) if today_raw else today_value
        result = replay_case(
            data,
            base_state=base_state,
            resolver=resolver_obj,
            compile_fn=compiler_fn,
            sql_builder=sql_builder_fn,
            today=today,
        )
        expected = data.get("expect", {})
        try:
            if expected.get("nql"):
                _assert_partial(expected["nql"], result.final_nql)
            if expected.get("snapshot"):
                _assert_partial(expected["snapshot"], result.snapshot)
            expected_error = expected.get("error")
            if expected_error:
                if not result.error_message:
                    raise AssertionError("Expected resolver error")
                fragment = expected_error.get("message_contains")
                if fragment and fragment not in result.error_message:
                    raise AssertionError(f"Error message missing fragment '{fragment}'")
            else:
                if result.error_message:
                    raise AssertionError(result.error_message)
            for fragment in expected.get("sql_contains", []) or []:
                if not result.sql or fragment not in result.sql:
                    raise AssertionError(f"Expected SQL to contain '{fragment}'")
            for fragment in expected.get("sql_not_contains", []) or []:
                if result.sql and fragment in result.sql:
                    raise AssertionError(f"Unexpected SQL fragment '{fragment}'")
        except AssertionError as exc:  # pragma: no cover - exercised via CLI
            _write_artifacts(case_id, result)
            results["failed"].append({"case": case_id, "reason": str(exc)})
        else:
            results["passed"].append(case_id)
    return results


__all__ = [
    "CASE_DIR",
    "load_all_cases",
    "replay_case",
    "run_cases_for_cli",
]
